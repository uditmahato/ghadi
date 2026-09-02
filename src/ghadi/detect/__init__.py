"""Detectors: the STA/LTA baseline, and (from M3) the learned classifier."""

from .onset import OnsetPick, pick_onset
from .sta_lta import StaLtaResult, Trigger, sta_lta, sta_lta_ratio

__all__ = [
    "OnsetPick",
    "StaLtaResult",
    "Trigger",
    "pick_onset",
    "sta_lta",
    "sta_lta_ratio",
]
