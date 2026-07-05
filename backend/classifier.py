"""
classifier.py

Wraps Google's YAMNet (via tensorflow_hub) to classify audio into a sound
label (e.g. "Footsteps", "Gunshot, gunfire", "Speech") with a confidence
score, for the overlay to display as subtitle text.

"""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

TARGET_SAMPLE_RATE = 16000  # YAMNet's required input rate

MIN_CONFIDENCE = 0.15

# Cap on how many simultaneous detections get returned per window (for terminal display).
MAX_DETECTIONS = 3

# Smoothing factor for per-class scores across windows, to reduce flicker in the
# top pick. 0.0 = no smoothing, 1.0 = never update
SCORE_SMOOTHING_ALPHA = 0.4

# How much a competing class's smoothed score must exceed the current
# "leader" class's smoothed score before it's allowed to take over as the
# displayed leader.
SWITCH_MARGIN = 0.05

DEFAULT_WINDOW_SECONDS = 1.0
DEFAULT_HOP_SECONDS = 0.1  # how often a new window becomes available

# YAMNet labels that describe an absence of sound rather than a sound worth
# surfacing as an event. These are never useful subtitle text.
EXCLUDED_LABELS = {"Silence"}

# How long a label must stay continuously above MIN_CONFIDENCE before it's
# considered ambience (background rain, engine drone, crowd noise, etc.)
# rather than a discrete event worth surfacing. Short one-off sounds never
# reach this, so it only catches things that just won't stop.
AMBIENT_PERSISTENCE_SECONDS = 4.0


@dataclass
class SoundDetection:
    label: str
    confidence: float
    active_seconds: float = 0.0   # how long this label has been continuously active
    is_ambient: bool = False      # True once active_seconds crosses AMBIENT_PERSISTENCE_SECONDS


@dataclass
class ClassificationResult:
    detections: List[SoundDetection]  # sorted by confidence descending, may be empty
    available: bool  # True if at least one detection cleared MIN_CONFIDENCE

    @property
    def top(self) -> Optional[SoundDetection]:
        return self.detections[0] if self.detections else None


def _downmix_to_mono(audio_block: np.ndarray) -> np.ndarray:
    float_block = audio_block.astype(np.float32) / 32768.0
    if float_block.ndim == 1:
        return float_block
    return float_block.mean(axis=1)


def _resample_linear(mono: np.ndarray, orig_sr: int, target_sr: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    if orig_sr == target_sr or len(mono) == 0:
        return mono
    duration_s = len(mono) / orig_sr
    target_len = max(int(round(duration_s * target_sr)), 1)
    orig_idx = np.linspace(0, len(mono) - 1, num=len(mono))
    target_idx = np.linspace(0, len(mono) - 1, num=target_len)
    return np.interp(target_idx, orig_idx, mono).astype(np.float32)


class RollingAudioBuffer:
    # Accumulates raw int16 audio blocks into a rolling buffer, and returns
    # a multichannel float32 window once enough audio has accumulated and
    # enough time has passed since the last window.
    def __init__(
        self,
        sample_rate: int,
        channels: int,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        hop_seconds: float = DEFAULT_HOP_SECONDS,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.window_frames = int(window_seconds * sample_rate)
        self.hop_frames = int(hop_seconds * sample_rate)
        self._buffer = np.zeros((0, channels), dtype=np.float32)  # native sample_rate, int16 scale
        self._frames_since_last_window = 0

    def add_block(self, audio_block: np.ndarray) -> Optional[np.ndarray]:
        # Add a new block of raw int16 audio (shape: frames x channels) to the rolling buffer.
        # Returns a multichannel float32 window (shape: window_frames x channels)
        block = audio_block.astype(np.float32)
        self._buffer = np.concatenate([self._buffer, block], axis=0)
        self._frames_since_last_window += len(block)

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
    # Wraps YAMNet to classify audio into sound labels with confidence scores.

    def __init__(self):
        self._model = None
        self._class_names: List[str] = []
        self._smoothed_scores: Optional[np.ndarray] = None  # persists across classify() calls
        self._sticky_leader_idx: Optional[int] = None  # persists across classify() calls
        self._active_since: Dict[int, float] = {}  # class idx -> monotonic time it became continuously active
        self._excluded_idx: set = set()  # class indices for EXCLUDED_LABELS, populated in _ensure_loaded

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import csv

        import tensorflow_hub as hub

        self._model = hub.load("https://tfhub.dev/google/yamnet/1")
        class_map_path = self._model.class_map_path().numpy().decode("utf-8")
        with open(class_map_path) as f:
            self._class_names = [row["display_name"] for row in csv.DictReader(f)]
        self._excluded_idx = {
            i for i, name in enumerate(self._class_names) if name in EXCLUDED_LABELS
        }

    def classify(self, mono_16k: np.ndarray) -> ClassificationResult:
        self._ensure_loaded()
        scores, _embeddings, _spectrogram = self._model(mono_16k)
        window_scores = scores.numpy().mean(axis=0)
        # Zero out excluded labels (e.g. "Silence") before smoothing/leader
        # selection so they can never be picked as a detection or sticky leader.
        for idx in self._excluded_idx:
            window_scores[idx] = 0.0

        # Smooth across windows (see SCORE_SMOOTHING_ALPHA) before picking
        # detections.
        if self._smoothed_scores is None:
            self._smoothed_scores = window_scores
        else:
            self._smoothed_scores = (
                SCORE_SMOOTHING_ALPHA * window_scores
                + (1 - SCORE_SMOOTHING_ALPHA) * self._smoothed_scores
            )

        # Pick the top detections, sorted by confidence, and apply hysteresis to
        # avoid flicker in the top pick.
        order = np.argsort(self._smoothed_scores)[::-1]
        candidate_idx = int(order[0])
        candidate_score = float(self._smoothed_scores[candidate_idx])

        # If the current top candidate is different from the previous "sticky" leader,
        # only switch if the new candidate is sufficiently better than the old leader.
        if self._sticky_leader_idx is None:
            self._sticky_leader_idx = candidate_idx
        elif candidate_idx != self._sticky_leader_idx:
            leader_score = float(self._smoothed_scores[self._sticky_leader_idx])
            if candidate_score > leader_score + SWITCH_MARGIN or leader_score < MIN_CONFIDENCE:
                self._sticky_leader_idx = candidate_idx

        now = time.monotonic()
        above_threshold = {
            int(idx) for idx in order if float(self._smoothed_scores[idx]) >= MIN_CONFIDENCE
        }
        # Start/stop the continuous-activity clock for each label so persistent
        # background sound (ambience) can be told apart from discrete events.
        for idx in above_threshold:
            if idx not in self._active_since:
                self._active_since[idx] = now
        for idx in list(self._active_since):
            if idx not in above_threshold:
                del self._active_since[idx]

        detections: List[SoundDetection] = []
        for idx in order[:MAX_DETECTIONS]:
            confidence = float(self._smoothed_scores[idx])
            if confidence < MIN_CONFIDENCE:
                break
            active_seconds = now - self._active_since[int(idx)]
            detections.append(SoundDetection(
                label=self._class_names[idx],
                confidence=confidence,
                active_seconds=active_seconds,
                is_ambient=active_seconds >= AMBIENT_PERSISTENCE_SECONDS,
            ))

        leader_label = self._class_names[self._sticky_leader_idx]
        for i, detection in enumerate(detections):
            if detection.label == leader_label and i != 0:
                detections.insert(0, detections.pop(i))
                break

        return ClassificationResult(detections=detections, available=len(detections) > 0)

    def classify_native_rate(self, multichannel_window: np.ndarray, native_sample_rate: int) -> ClassificationResult:
        mono = _downmix_to_mono(multichannel_window)
        resampled = _resample_linear(mono, native_sample_rate)
        return self.classify(resampled)


if __name__ == "__main__":
    print("Loading YAMNet (downloads on first run, needs internet)...")
    classifier = YamNetClassifier()

    silence = np.zeros(TARGET_SAMPLE_RATE, dtype=np.float32)
    print("Silence ->", classifier.classify(silence).detections)

    rng = np.random.default_rng(0)
    noise = rng.uniform(-0.3, 0.3, size=TARGET_SAMPLE_RATE).astype(np.float32)
    print("White noise ->", classifier.classify(noise).detections)