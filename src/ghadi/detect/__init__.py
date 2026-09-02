"""Detectors: the STA/LTA baseline, and (from M3) the learned classifier."""

from .sta_lta import StaLtaResult, Trigger, sta_lta, sta_lta_ratio

__all__ = ["StaLtaResult", "Trigger", "sta_lta", "sta_lta_ratio"]
