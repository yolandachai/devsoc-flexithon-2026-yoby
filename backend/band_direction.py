"""
band_direction.py

Splits multichannel audio into frequency bands and estimates direction per
band, instead of a single broadband direction for the whole mixed signal.

IMPORTANT LIMITATION: this is NOT true source separation. If two sounds
occupy the SAME frequency band at the same time, they still blend together
in that band's direction estimate.
"""

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
from scipy import signal as scipy_signal

from direction import DirectionEstimate, estimate_direction


# Minimum share of total cross-band energy a band must carry before its
# direction estimate is trusted.
MIN_BAND_ENERGY_FRACTION = 0.05

BANDS = [
    ("sub_low", 20, 150),
    ("low", 150, 500),
    ("mid", 500, 2000),
    ("high", 2000, 6000),
    ("ultra", 6000, 16000),
]

# Heuristic mapping of sound labels to the frequency band(s) they most likely occupy, 
# for the purpose of picking a direction estimate from the right band. This is 
# not a perfect science, just a rough guide to avoid picking a direction from
# a band that is unlikely to contain the sound in question.
LABEL_BAND_HINTS = [
    ("footstep", "low"),
    ("walk", "low"),
    ("run", "low"),
    ("gunshot", "high"),
    ("gunfire", "high"),
    ("explosion", "sub_low"),
    ("door", "low"),
    ("glass", "ultra"),
    ("speech", "mid"),
    ("conversation", "mid"),
    ("insect", "ultra"),
    ("cricket", "ultra"),
    ("bird", "high"),
    ("wind", "sub_low"),
    ("engine", "sub_low"),
    ("music", "mid"),
]


def _build_filters(sample_rate: int) -> Dict[str, np.ndarray]:
    nyq = sample_rate / 2.0
    filters = {}
    for name, lo, hi in BANDS:
        lo_n, hi_n = max(lo / nyq, 0.001), min(hi / nyq, 0.999)
        if lo_n < hi_n:
            filters[name] = scipy_signal.butter(8, [lo_n, hi_n], btype="band", output="sos")
    return filters


@dataclass
class BandDirections:
    # Direction estimates per band, keyed by band name (e.g. "low", "mid", "high").
    directions: Dict[str, DirectionEstimate]

    def for_label(self, label: str) -> DirectionEstimate:
        # Pick the most relevant band for this label, if any, and return its direction estimate.
        label_lower = label.lower()
        for hint, band_name in LABEL_BAND_HINTS:
            if hint in label_lower and band_name in self.directions:
                estimate = self.directions[band_name]
                if estimate.available:
                    return estimate

        available = [d for d in self.directions.values() if d.available]
        if not available:
            return DirectionEstimate(available=False, mode="none", label="unknown")
        return max(available, key=lambda d: d.confidence)


class BandDirectionEstimator:
    # Splits multichannel audio into frequency bands and estimates direction per
    # band, instead of a single broadband direction for the whole mixed signal.

    def __init__(self):
        self._filters_by_rate: Dict[int, Dict[str, np.ndarray]] = {}

    def estimate(
        self,
        multichannel_window: np.ndarray,
        channel_labels: List[str],
        sample_rate: int,
    ) -> BandDirections:
        if sample_rate not in self._filters_by_rate:
            self._filters_by_rate[sample_rate] = _build_filters(sample_rate)
        filters = self._filters_by_rate[sample_rate]

        directions: Dict[str, DirectionEstimate] = {}
        band_energy: Dict[str, float] = {}
        for band_name, sos in filters.items():
            # Filter the multichannel window into this band's frequency range,
            # then estimate direction from the filtered signal.
            filtered = scipy_signal.sosfiltfilt(sos, multichannel_window, axis=0)
            band_levels = list(np.sqrt(np.mean(filtered ** 2, axis=0)))
            directions[band_name] = estimate_direction(band_levels, channel_labels)
            band_energy[band_name] = sum(band_levels)

        # A band that carries only a sliver of the total energy across all bands
        # can still produce a confident-looking direction (e.g. stereo pan is a
        # ratio, independent of absolute level) purely from noise.
        total_energy = sum(band_energy.values())
        if total_energy > 0:
            for band_name, estimate in directions.items():
                if estimate.available and band_energy[band_name] / total_energy < MIN_BAND_ENERGY_FRACTION:
                    directions[band_name] = DirectionEstimate(
                        available=False, mode="none", label="low energy band"
                    )

        return BandDirections(directions=directions)


if __name__ == "__main__":
    # Smoke test: generate a stereo signal with a low tone panned left and a high tone panned
    # right, and see if the per-band direction estimates reflect that.
    sample_rate = 48000
    duration_s = 1.0
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)

    low_tone = np.sin(2 * np.pi * 100 * t)   # falls in the "low" band, 150 Hz ceiling is close but 100Hz test tone will fall in sub_low/low boundary -- fine for a smoke test
    high_tone = np.sin(2 * np.pi * 8000 * t)  # falls in the "ultra" band

    # Low tone panned left: strong in left channel, weak in right.
    # High tone panned right: strong in right channel, weak in left.
    left = 1.0 * low_tone + 0.05 * high_tone
    right = 0.05 * low_tone + 1.0 * high_tone
    stereo_window = np.stack([left, right], axis=1).astype(np.float32) * 10000  # int16-ish scale

    estimator = BandDirectionEstimator()
    result = estimator.estimate(stereo_window, ["Left", "Right"], sample_rate)

    print("Per-band direction estimates (mixed low-left + high-right tones):")
    for band_name, est in result.directions.items():
        print(f"  {band_name}: {est}")