"""
classifier.py

Wraps Google's YAMNet (via tensorflow_hub) to classify audio into a sound
label (e.g. "Footsteps", "Gunshot, gunfire", "Speech") with a confidence
score, for the overlay to display as subtitle text.

YAMNet expects mono 16 kHz float32 audio in roughly ~1 second windows to
produce a meaningful label -- audio_capture's per-block chunks (~1024
frames, ~20ms) are far too short on their own. RollingAudioBuffer
accumulates blocks into windows; YamNetClassifier classifies each window
once it's ready.

Setup notes:
- First use downloads the model (~15MB) from tfhub.dev and caches it
  locally (TFHUB_CACHE_DIR, or the OS default temp/cache dir) -- needs
  internet access once, works offline after that.
- Requires `tensorflow` and `tensorflow_hub` (see requirements.txt). These
  are heavy dependencies; expect a slow first import.
- NOT smoke-tested end-to-end yet -- the dev sandbox this was written in
  can't reach tfhub.dev to download the model or verify inference. Please
  run `python classifier.py` once on your machine (internet required for
  the first run) to confirm it loads and classifies before wiring it
  further into main.py.
"""

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

TARGET_SAMPLE_RATE = 16000  # YAMNet's required input rate

# Minimum confidence for a class to be considered "detected" at all.
MIN_CONFIDENCE = 0.15

# Cap on how many simultaneous detections get returned per window, sorted
# by confidence descending, so a busy scene doesn't dump 20 marginal labels.
MAX_DETECTIONS = 3

SCORE_SMOOTHING_ALPHA = 0.4

SWITCH_MARGIN = 0.05

DEFAULT_WINDOW_SECONDS = 1.0
DEFAULT_HOP_SECONDS = 0.5  # how often a new window becomes available


@dataclass
class SoundDetection:
    label: str
    confidence: float


@dataclass
class ClassificationResult:
    detections: List[SoundDetection]  # sorted by confidence descending, may be empty
    available: bool  # True if at least one detection cleared MIN_CONFIDENCE

    @property
    def top(self) -> Optional[SoundDetection]:
        return self.detections[0] if self.detections else None


def _downmix_to_mono(audio_block: np.ndarray) -> np.ndarray:
    """int16 (frames, channels) or (frames,) -> float32 mono in [-1.0, 1.0]."""
    float_block = audio_block.astype(np.float32) / 32768.0
    if float_block.ndim == 1:
        return float_block
    return float_block.mean(axis=1)


def _resample_linear(mono: np.ndarray, orig_sr: int, target_sr: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    """
    Simple linear-interpolation resample -- no anti-aliasing filter, so
    quality is lower than a proper polyphase resample (e.g. scipy's
    resample_poly). Adequate for feeding a classifier rather than for
    anything perceptual; swap in scipy if classification accuracy suffers
    and a dependency is acceptable.
    """
    if orig_sr == target_sr or len(mono) == 0:
        return mono
    duration_s = len(mono) / orig_sr
    target_len = max(int(round(duration_s * target_sr)), 1)
    orig_idx = np.linspace(0, len(mono) - 1, num=len(mono))
    target_idx = np.linspace(0, len(mono) - 1, num=target_len)
    return np.interp(target_idx, orig_idx, mono).astype(np.float32)


class RollingAudioBuffer:
    """
    Accumulates raw per-block audio (as read from the WASAPI stream) into
    fixed-size, overlapping windows suitable for classification.
    """

    def __init__(
        self,
        sample_rate: int,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        hop_seconds: float = DEFAULT_HOP_SECONDS,
    ):
        self.sample_rate = sample_rate
        self.window_frames = int(window_seconds * sample_rate)
        self.hop_frames = int(hop_seconds * sample_rate)
        self._buffer = np.zeros((0,), dtype=np.float32)  # mono, at native sample_rate
        self._frames_since_last_window = 0

    def add_block(self, audio_block: np.ndarray) -> Optional[np.ndarray]:
        # Add a new block of raw audio (int16, interleaved channels) to the buffer.
        # Returns a new window (float32, mono, native sample_rate) if enough audio has accumulated.
        mono = _downmix_to_mono(audio_block)
        self._buffer = np.concatenate([self._buffer, mono])
        self._frames_since_last_window += len(mono)

        # Cap buffer growth even before the first full window.
        max_len = self.window_frames * 2
        if len(self._buffer) > max_len:
            self._buffer = self._buffer[-max_len:]

        if len(self._buffer) < self.window_frames:
            return None
        if self._frames_since_last_window < self.hop_frames:
            return None

        self._frames_since_last_window = 0
        return self._buffer[-self.window_frames:].copy()


class YamNetClassifier:
    """
    Wraps YAMNet (via tensorflow_hub) to classify audio into a sound label
    (e.g. "Footsteps", "Gunshot, gunfire", "Speech") with a confidence score.
    """

    def __init__(self):
        self._model = None
        self._class_names: List[str] = []
        self._smoothed_scores: Optional[np.ndarray] = None  # persists across classify() calls
        self._sticky_leader_idx: Optional[int] = None  # persists across classify() calls

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import csv

        import tensorflow_hub as hub

        self._model = hub.load("https://tfhub.dev/google/yamnet/1")
        class_map_path = self._model.class_map_path().numpy().decode("utf-8")
        with open(class_map_path) as f:
            self._class_names = [row["display_name"] for row in csv.DictReader(f)]

    def classify(self, mono_16k: np.ndarray) -> ClassificationResult:
        """mono_16k: mono float32 audio already resampled to 16kHz."""
        self._ensure_loaded()
        scores, _embeddings, _spectrogram = self._model(mono_16k)
        window_scores = scores.numpy().mean(axis=0)

        # Smooth across windows (see SCORE_SMOOTHING_ALPHA) before picking
        # detections, not after, so the smoothing doesn't hide a genuine
        # near-tie between two classes that should both be detected.
        if self._smoothed_scores is None:
            self._smoothed_scores = window_scores
        else:
            self._smoothed_scores = (
                SCORE_SMOOTHING_ALPHA * window_scores
                + (1 - SCORE_SMOOTHING_ALPHA) * self._smoothed_scores
            )

        # Multiple classes can legitimately be "detected" on the same
        # window (YAMNet's per-class scores aren't mutually exclusive)
        order = np.argsort(self._smoothed_scores)[::-1]
        candidate_idx = int(order[0])
        candidate_score = float(self._smoothed_scores[candidate_idx])

        # Hysteresis: only let a new class take over the "leader" spot
        if self._sticky_leader_idx is None:
            self._sticky_leader_idx = candidate_idx
        elif candidate_idx != self._sticky_leader_idx:
            leader_score = float(self._smoothed_scores[self._sticky_leader_idx])
            if candidate_score > leader_score + SWITCH_MARGIN or leader_score < MIN_CONFIDENCE:
                self._sticky_leader_idx = candidate_idx

        detections: List[SoundDetection] = []
        for idx in order[:MAX_DETECTIONS]:
            confidence = float(self._smoothed_scores[idx])
            if confidence < MIN_CONFIDENCE:
                break
            detections.append(SoundDetection(label=self._class_names[idx], confidence=confidence))

        # Put the sticky leader first if it made the cut, even if it's not
        # numerically first this instant
        leader_label = self._class_names[self._sticky_leader_idx]
        for i, detection in enumerate(detections):
            if detection.label == leader_label and i != 0:
                detections.insert(0, detections.pop(i))
                break

        return ClassificationResult(detections=detections, available=len(detections) > 0)

    def classify_native_rate(self, mono: np.ndarray, native_sample_rate: int) -> ClassificationResult:
        """Convenience: resample from native_sample_rate to 16kHz, then classify."""
        resampled = _resample_linear(mono, native_sample_rate)
        return self.classify(resampled)


if __name__ == "__main__":
    # Minimal manual check
    print("Loading YAMNet (downloads on first run, needs internet)...")
    classifier = YamNetClassifier()

    silence = np.zeros(TARGET_SAMPLE_RATE, dtype=np.float32)
    print("Silence ->", classifier.classify(silence).detections)

    rng = np.random.default_rng(0)
    noise = rng.uniform(-0.3, 0.3, size=TARGET_SAMPLE_RATE).astype(np.float32)
    print("White noise ->", classifier.classify(noise).detections)