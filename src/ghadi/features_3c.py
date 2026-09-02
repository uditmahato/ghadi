"""Three-component discriminants (issue 2.5).

**Why this module matters more than it first appeared.** exp003 measured the two
spectral features against 64 real earthquakes and found 12.5% of them meet the
cascade's values on both. Those two features encode *the same physical idea* — a slow,
spatially extended, low-stress-drop source is depleted at high frequency — from two
angles, so they are correlated and they fail together. GHADI needs a discriminant that
fails independently, and how a source partitions energy between components is one.

The physics:

- A tectonic earthquake nucleates at depth. Its P wave arrives from below at steep
  incidence, so first-arrival energy concentrates on the **vertical** component and is
  strongly **rectilinear** — the particle motion is close to a straight line along the
  ray.
- A mass movement is a *surface* process. It is an inefficient generator of body waves
  and an efficient generator of surface waves, which are elliptical (Rayleigh) or purely
  transverse (Love). That yields relatively more **horizontal** energy, lower
  rectilinearity, and a shallower apparent incidence angle.

So the expected ordering is: earthquakes high rectilinearity and low H/V; mass movements
lower rectilinearity and higher H/V. **That is a hypothesis, not a result** — it has not
yet been measured on the corpus, because the corpus is BHZ-only (see the data card).
Nothing here should be quoted as a finding until it has been.

Detection path: numpy only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Polarisation:
    """Particle-motion descriptors from the 3C covariance matrix."""

    rectilinearity: float  # 1 = motion along a line; 0 = isotropic
    planarity: float  # 1 = motion confined to a plane
    incidence_deg: float  # 0 = vertical (from below), 90 = horizontal
    azimuth_deg: float  # of the dominant motion axis, degrees east of north
    hv_ratio: float  # horizontal energy over vertical energy

    def as_dict(self) -> dict[str, float]:
        return {
            "rectilinearity": self.rectilinearity,
            "planarity": self.planarity,
            "incidence_deg": self.incidence_deg,
            "azimuth_deg": self.azimuth_deg,
            "hv_ratio": self.hv_ratio,
        }


def hv_ratio(z: np.ndarray, n: np.ndarray, e: np.ndarray) -> float:
    """Horizontal-to-vertical energy ratio.

    Surface-wave-rich sources put proportionally more energy on the horizontals than a
    steeply-incident body-wave arrival does.
    """
    vertical = float(np.mean(np.asarray(z, dtype=float) ** 2))
    horizontal = float(
        np.mean(np.asarray(n, dtype=float) ** 2) + np.mean(np.asarray(e, dtype=float) ** 2)
    )
    if vertical <= 0:
        return float("nan")
    return math.sqrt(horizontal / vertical)


def polarisation(z: np.ndarray, n: np.ndarray, e: np.ndarray) -> Polarisation:
    """Eigen-decomposition of the 3C covariance matrix.

    The eigenvector of the largest eigenvalue is the dominant axis of particle motion;
    the eigenvalue spectrum says how linear or planar that motion is.
    """
    z = np.asarray(z, dtype=float)
    n = np.asarray(n, dtype=float)
    e = np.asarray(e, dtype=float)
    if not (z.size == n.size == e.size):
        raise ValueError("the three components must be the same length")
    if z.size < 2:
        raise ValueError("need at least two samples to form a covariance")

    data = np.vstack([z - z.mean(), n - n.mean(), e - e.mean()])
    covariance = np.cov(data)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)

    order = np.argsort(eigenvalues)[::-1]  # descending
    lam = eigenvalues[order]
    principal = eigenvectors[:, order[0]]

    lam = np.clip(lam, 0.0, None)
    if lam[0] <= 0:
        nan = float("nan")
        return Polarisation(nan, nan, nan, nan, hv_ratio(z, n, e))

    rectilinearity = float(1.0 - (lam[1] + lam[2]) / (2.0 * lam[0]))
    planarity = (
        float(1.0 - 2.0 * lam[2] / (lam[0] + lam[1])) if (lam[0] + lam[1]) > 0 else float("nan")
    )

    # principal is (Z, N, E). Incidence is measured from vertical.
    vertical_component = abs(float(principal[0]))
    horizontal_magnitude = math.hypot(float(principal[1]), float(principal[2]))
    incidence_deg = math.degrees(math.atan2(horizontal_magnitude, vertical_component))
    azimuth_deg = math.degrees(math.atan2(float(principal[2]), float(principal[1]))) % 360.0

    return Polarisation(
        rectilinearity=rectilinearity,
        planarity=planarity,
        incidence_deg=incidence_deg,
        azimuth_deg=azimuth_deg,
        hv_ratio=hv_ratio(z, n, e),
    )


def polarisation_over_window(
    z: np.ndarray,
    n: np.ndarray,
    e: np.ndarray,
    sampling_rate: float,
    onset_s: float,
    duration_s: float = 20.0,
) -> Polarisation:
    """Polarisation over a bounded segment starting at the onset.

    Bounded for the reason exp002 established for ``emergence_s``: a descriptor of an
    arrival must be computed over that arrival, not over everything that follows it.
    Averaged across a whole window, polarisation collapses toward the isotropic value
    of whatever noise dominates.
    """
    start = max(round(onset_s * sampling_rate), 0)
    end = min(start + round(duration_s * sampling_rate), z.size)
    if end - start < 2:
        nan = float("nan")
        return Polarisation(nan, nan, nan, nan, nan)
    return polarisation(z[start:end], n[start:end], e[start:end])
