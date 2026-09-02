"""Independence-grouped corroboration, cost-loss thresholds, and alert tiering.

Two rules do the work here (HANDOFF §4):

**Corroboration requires source independence, not agreement count.** Two channels fed
by the same sensor are one channel. Channels declare an ``independence_group``; the
fusion layer collapses each group to its strongest member *before* combining, so
duplicating a feed cannot manufacture confidence.

**Degradation is a first-class output, never a silent state.** Four of five gauges died
on 26 August 2026. Every decision carries ``channels_alive`` and ``channels_dead``, and
the alert text says so. A system that quietly loses a channel is worse than one that
fails loudly, because it is confidently wrong.

Latency budget: < 50 ms. Detection path — no heavy imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .config import DEFAULT, FusionConfig


class Tier(StrEnum):
    """Alert tiers, in increasing severity."""

    NONE = "NONE"
    WATCH = "WATCH"
    ADVISORY = "ADVISORY"
    WARNING = "WARNING"


@dataclass(frozen=True)
class Channel:
    """One evidence channel entering fusion."""

    name: str
    probability: float  # calibrated P(mass movement | this channel)
    independence_group: str  # channels sharing a group share a failure mode
    alive: bool = True
    detail: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError(f"{self.name}: probability must be in [0, 1]")


@dataclass(frozen=True)
class Decision:
    """A fused decision. Never a bare score — always with what produced it."""

    tier: Tier
    probability: float
    channels_alive: tuple[str, ...]
    channels_dead: tuple[str, ...]
    independent_groups: int
    rationale: str
    degraded: bool
    config: FusionConfig = field(default_factory=lambda: DEFAULT.fusion)

    @property
    def degradation_note(self) -> str:
        """Human-readable degradation statement for inclusion in every alert."""
        if not self.channels_dead:
            return f"All {len(self.channels_alive)} channels reporting."
        return (
            f"DEGRADED: {len(self.channels_dead)} of "
            f"{len(self.channels_alive) + len(self.channels_dead)} channels offline "
            f"({', '.join(self.channels_dead)}). "
            f"Live: {', '.join(self.channels_alive) or 'none'}."
        )


def _noisy_or(probabilities: list[float]) -> float:
    """P(at least one true), assuming the inputs are independent."""
    complement = 1.0
    for p in probabilities:
        complement *= 1.0 - p
    return 1.0 - complement


def fuse(channels: list[Channel], config: FusionConfig | None = None) -> Decision:
    """Fuse evidence channels into a tiered decision.

    Independence groups are collapsed to their strongest live member before the
    noisy-OR, so two feeds off one sensor count once.
    """
    config = config or DEFAULT.fusion

    live = [c for c in channels if c.alive]
    dead = [c for c in channels if not c.alive]

    if not live:
        return Decision(
            tier=Tier.NONE,
            probability=0.0,
            channels_alive=(),
            channels_dead=tuple(c.name for c in dead),
            independent_groups=0,
            rationale="no live channels — the system is blind and says so",
            degraded=True,
            config=config,
        )

    strongest: dict[str, Channel] = {}
    for channel in live:
        current = strongest.get(channel.independence_group)
        if current is None or channel.probability > current.probability:
            strongest[channel.independence_group] = channel

    representatives = list(strongest.values())
    probability = _noisy_or([c.probability for c in representatives])
    n_groups = len(representatives)

    if probability >= config.warning_p and n_groups >= config.min_groups_for_warning:
        tier = Tier.WARNING
        why = (
            f"p={probability:.2f} >= {config.warning_p:.2f} with {n_groups} independent "
            f"groups (>= {config.min_groups_for_warning} required)"
        )
    elif probability >= config.advisory_p:
        tier = Tier.ADVISORY
        why = f"p={probability:.2f} >= {config.advisory_p:.2f}"
        if n_groups < config.min_groups_for_warning:
            why += (
                f"; held below WARNING — only {n_groups} independent group(s), "
                "corroboration requirement not met"
            )
    elif probability >= config.watch_p:
        tier = Tier.WATCH
        why = f"p={probability:.2f} >= {config.watch_p:.2f}"
    else:
        tier = Tier.NONE
        why = f"p={probability:.2f} below watch threshold {config.watch_p:.2f}"

    return Decision(
        tier=tier,
        probability=probability,
        channels_alive=tuple(c.name for c in live),
        channels_dead=tuple(c.name for c in dead),
        independent_groups=n_groups,
        rationale=why,
        degraded=bool(dead),
        config=config,
    )
