"""
direction.py

Estimates sound direction from per-channel audio levels.

Two paths depending on channel count:

- Stereo (2ch): pan estimate (-1.0 left to +1.0 right) from L/R energy
  difference. Stereo cannot represent front/back or elevation, only
  left/right balance.
- Multichannel (8ch, 7.1 layout): azimuth estimate (degrees, 0 = front,
  positive = clockwise toward the right) via weighted vector sum of
  channel energies at their known speaker angles.

Levels are expected as linear RMS values (not dBFS) -- vector-sum
weighting assumes non-negative, energy-proportional inputs.
"""

import math
from dataclasses import dataclass
from typing import List, Optional

# Speaker azimuth angles in degrees, 0 = front center, positive = clockwise
# (toward the right), following common 7.1 speaker layouts. Exact angles
# vary by convention/manufacturer, treat as a default.
# LFE has no directional meaning and is excluded from azimuth estimation.
CHANNEL_ANGLES_8 = {
    "Front-L": -30.0,
    "Front-R": 30.0,
    "Center": 0.0,
    "LFE": None,
    "Rear-L": -150.0,
    "Rear-R": 150.0,
    "Side-L": -90.0,
    "Side-R": 90.0,
}

# Total linear RMS energy below which a direction estimate is treated as
# unreliable (near-silence). Approximate starting point -- tune against
# real capture data.
SILENCE_THRESHOLD = 15.0


@dataclass
class DirectionEstimate:
    available: bool                       # False if too quiet, or channel count unsupported
    mode: str                             # "stereo", "multichannel", or "none"
    pan: Optional[float] = None           # -1.0 (left) to 1.0 (right), stereo mode only
    azimuth_deg: Optional[float] = None   # -180 to 180, multichannel mode only
    confidence: float = 0.0               # 0.0-1.0, meaning differs by mode (see below)
    label: str = "unknown"                # human-readable, e.g. "left", "back-right", "center"


"""Dispatch to the appropriate direction estimation method based on channel count."""
def estimate_direction(levels: List[float], channel_labels: List[str]) -> DirectionEstimate:
    total_energy = sum(levels)
    if total_energy < SILENCE_THRESHOLD:
        return DirectionEstimate(available=False, mode="none", label="silent")

    if len(levels) == 2:
        return _estimate_stereo(levels)

    if len(levels) == 8:
        return _estimate_multichannel(levels, channel_labels)

    return DirectionEstimate(available=False, mode="none", label="unsupported channel count")


def _estimate_stereo(levels: List[float]) -> DirectionEstimate:
    left, right = levels
    total = left + right
    pan = (right - left) / total  # -1.0 = full left, +1.0 = full right

    return DirectionEstimate(
        available=True,
        mode="stereo",
        pan=pan,
        # Confidence scales with how strongly panned the signal is: near
        # 0 means it's audible on both sides (ambiguous direction), near
        # 1 means it's strongly localized to one side.
        confidence=abs(pan),
        label=_pan_label(pan),
    )


def _pan_label(pan: float) -> str:
    if pan < -0.6:
        return "left"
    if pan < -0.2:
        return "slightly left"
    if pan <= 0.2:
        return "center"
    if pan <= 0.6:
        return "slightly right"
    return "right"


def _estimate_multichannel(levels: List[float], channel_labels: List[str]) -> DirectionEstimate:
    x_sum = 0.0
    y_sum = 0.0
    total_energy = 0.0

    for level, label in zip(levels, channel_labels):
        angle = CHANNEL_ANGLES_8.get(label)
        if angle is None:  # LFE or unrecognized channel, no directional contribution
            continue
        angle_rad = math.radians(angle)
        x_sum += level * math.cos(angle_rad)
        y_sum += level * math.sin(angle_rad)
        total_energy += level

    if total_energy == 0:
        return DirectionEstimate(available=False, mode="none", label="silent")

    azimuth_deg = math.degrees(math.atan2(y_sum, x_sum))

    # Vector magnitude relative to total energy: near 1.0 means energy is
    # concentrated in one direction (a clear point source), near 0.0 means
    # energy is spread evenly across channels (diffuse ambience/music, no
    # real direction to report even though the signal is loud).
    magnitude = math.sqrt(x_sum ** 2 + y_sum ** 2)
    confidence = min(magnitude / total_energy, 1.0)

    return DirectionEstimate(
        available=True,
        mode="multichannel",
        azimuth_deg=azimuth_deg,
        confidence=confidence,
        label=_azimuth_label(azimuth_deg),
    )


def _azimuth_label(azimuth_deg: float) -> str:
    angle = azimuth_deg % 360
    buckets = [
        (22.5, 67.5, "front-right"),
        (67.5, 112.5, "right"),
        (112.5, 157.5, "back-right"),
        (157.5, 202.5, "back"),
        (202.5, 247.5, "back-left"),
        (247.5, 292.5, "left"),
        (292.5, 337.5, "front-left"),
    ]
    for lo, hi, name in buckets:
        if lo <= angle < hi:
            return name
    return "front"


if __name__ == "__main__":
    stereo_labels = ["Left", "Right"]
    multichannel_labels = [
        "Front-L", "Front-R", "Center", "LFE",
        "Rear-L", "Rear-R", "Side-L", "Side-R",
    ]

    print("Stereo cases:")
    for levels in [[100, 10], [10, 100], [50, 50], [0, 0]]:
        print(f"  levels={levels} -> {estimate_direction(levels, stereo_labels)}")

    print("\nMultichannel cases:")
    for levels in [
        [100, 0, 0, 0, 0, 0, 0, 0],        # front-left only
        [0, 0, 0, 0, 100, 0, 0, 0],        # rear-left only
        [50, 50, 50, 0, 0, 0, 0, 0],       # front cluster
        [30, 30, 30, 0, 30, 30, 30, 30],   # even everywhere -- diffuse
    ]:
        print(f"  levels={levels} -> {estimate_direction(levels, multichannel_labels)}")