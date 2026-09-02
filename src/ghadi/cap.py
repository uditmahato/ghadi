"""CAP 1.2 alert emission with machine-readable provenance.

Two hard safety rules are enforced here in code, not in review (HANDOFF §15):

1. ``status`` must never be ``Actual`` and ``scope`` must never be ``Public`` in any
   non-authorised build. An authorised build sets ``GHADI_AUTHORIZED_BUILD=1``, which
   should only ever be true where an alerting authority has signed off. There is a
   test for this. Do not skip it.
2. **No generative model ever produces a number.** All text below is a strict template
   with values injected from structured records. If you find yourself passing a
   free-text field into this module from a language model, stop.

Every alert records the exact model version that produced it, and states which channels
were alive — a degraded detection that does not say it is degraded is confidently wrong.

Latency budget: < 50 ms.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from .config import DEFAULT, CapConfig, is_authorized_build
from .fusion import Decision, Tier

CAP_NAMESPACE = "urn:oasis:names:tc:emergency:cap:1.2"

# The alert is built with unqualified tags plus a default xmlns, which serialises to
# correct CAP 1.2. Note the asymmetry that follows: on the element returned by
# build_cap you query ``alert.find("status")``, but once the XML has been *parsed*
# back the default namespace applies to every descendant and you must query
# ``root.find("cap:status", CAP_NS)``. Consumers parse, so they need this map.
CAP_NS = {"cap": CAP_NAMESPACE}

# CAP <severity> per tier. Deliberately conservative: a WATCH is not "Severe".
_TIER_SEVERITY = {
    Tier.NONE: "Unknown",
    Tier.WATCH: "Minor",
    Tier.ADVISORY: "Moderate",
    Tier.WARNING: "Severe",
}
_TIER_URGENCY = {
    Tier.NONE: "Unknown",
    Tier.WATCH: "Future",
    Tier.ADVISORY: "Expected",
    Tier.WARNING: "Immediate",
}


class CapSafetyError(RuntimeError):
    """An attempt to emit a live public alert from a non-authorised build."""


@dataclass(frozen=True)
class AlertContext:
    """Everything the templates may inject. All values come from structured records."""

    event_id: str
    detected_utc: datetime
    river_reach: str
    model_version: str
    settlements: tuple[str, ...] = ()
    arrival_estimates_min: dict[str, float] | None = None
    exposed_population: int | None = None


def _require_safe(status: str, scope: str) -> None:
    if status == "Actual" and not is_authorized_build():
        raise CapSafetyError(
            "status='Actual' requires GHADI_AUTHORIZED_BUILD=1. This build is not "
            "authorised to emit live alerts (HANDOFF §15 rule 1)."
        )
    if scope == "Public" and not is_authorized_build():
        raise CapSafetyError(
            "scope='Public' requires GHADI_AUTHORIZED_BUILD=1. This build is not "
            "authorised to emit public alerts (HANDOFF §15 rule 1)."
        )


def _headline(decision: Decision, context: AlertContext) -> str:
    return f"{decision.tier.value}: possible surge on {context.river_reach}"


def _description(decision: Decision, context: AlertContext) -> str:
    """Strict template. Every number is injected from a structured record."""
    detected = context.detected_utc.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [
        f"A mass-movement signal was detected at {detected} affecting {context.river_reach}.",
        f"Fused confidence {decision.probability:.2f} from {decision.independent_groups} "
        f"independent evidence group(s).",
        decision.degradation_note,
    ]
    if context.arrival_estimates_min:
        for settlement, minutes in sorted(context.arrival_estimates_min.items()):
            lines.append(f"Estimated arrival at {settlement}: {minutes:.0f} minutes.")
    if context.exposed_population is not None:
        lines.append(f"Estimated exposed population: {context.exposed_population}.")
    lines.append("This is a detection, not a forecast. Confirm before acting where possible.")
    return " ".join(lines)


def _instruction(decision: Decision) -> str:
    if decision.tier is Tier.WARNING:
        return "Move away from the river channel to higher ground immediately."
    if decision.tier is Tier.ADVISORY:
        return "Prepare to move away from the river channel. Await confirmation."
    return "Monitor official channels. No action required at this time."


def build_cap(
    decision: Decision,
    context: AlertContext,
    config: CapConfig | None = None,
    status: str | None = None,
    scope: str | None = None,
) -> ET.Element:
    """Build a CAP 1.2 ``<alert>`` element.

    Defaults are ``status='Test'`` and ``scope='Restricted'``; overriding either to a
    live value requires an authorised build.
    """
    config = config or DEFAULT.cap
    status = status or config.default_status
    scope = scope or config.default_scope
    _require_safe(status, scope)

    sent = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    alert = ET.Element("alert", xmlns=CAP_NAMESPACE)
    ET.SubElement(
        alert, "identifier"
    ).text = f"{config.identifier_prefix}-{context.event_id}-{uuid.uuid4().hex[:8]}"
    ET.SubElement(alert, "sender").text = config.sender
    ET.SubElement(alert, "sent").text = sent
    ET.SubElement(alert, "status").text = status
    ET.SubElement(alert, "msgType").text = "Alert"
    ET.SubElement(alert, "scope").text = scope

    info = ET.SubElement(alert, "info")
    ET.SubElement(info, "language").text = config.default_language_en
    ET.SubElement(info, "category").text = "Geo"
    ET.SubElement(info, "event").text = "Cascading flood surge"
    ET.SubElement(info, "urgency").text = _TIER_URGENCY[decision.tier]
    ET.SubElement(info, "severity").text = _TIER_SEVERITY[decision.tier]
    ET.SubElement(info, "certainty").text = "Possible" if decision.degraded else "Likely"
    ET.SubElement(info, "headline").text = _headline(decision, context)
    ET.SubElement(info, "description").text = _description(decision, context)
    ET.SubElement(info, "instruction").text = _instruction(decision)

    # Machine-readable provenance: what produced this, and on what evidence.
    for name, value in (
        ("ghadi:model_version", context.model_version),
        ("ghadi:tier", decision.tier.value),
        ("ghadi:probability", f"{decision.probability:.4f}"),
        ("ghadi:independent_groups", str(decision.independent_groups)),
        ("ghadi:channels_alive", ",".join(decision.channels_alive) or "none"),
        ("ghadi:channels_dead", ",".join(decision.channels_dead) or "none"),
        ("ghadi:rationale", decision.rationale),
        ("ghadi:cost_ratio_miss_over_fa", f"{decision.config.cost_miss_over_false_alarm:g}"),
    ):
        parameter = ET.SubElement(info, "parameter")
        ET.SubElement(parameter, "valueName").text = name
        ET.SubElement(parameter, "value").text = value

    area = ET.SubElement(info, "area")
    settlements = f" ({', '.join(context.settlements)})" if context.settlements else ""
    ET.SubElement(area, "areaDesc").text = f"{context.river_reach}{settlements}"
    return alert


def to_xml(alert: ET.Element) -> str:
    """Serialise a CAP element to a UTF-8 XML string."""
    ET.indent(alert, space="  ")
    return ET.tostring(alert, encoding="unicode", xml_declaration=True)
