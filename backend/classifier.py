"""
classifier.py

Wraps Google's YAMNet (via tensorflow_hub) to classify audio into a sound
label (e.g. "Footsteps", "Gunshot, gunfire", "Speech") with a confidence
score, for the overlay to display as subtitle text.

"""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

import numpy as np

TARGET_SAMPLE_RATE = 16000  # YAMNet's required input rate

MIN_CONFIDENCE = 0.15

# Cap on how many simultaneous detections get returned per window (for terminal display).
# Kept low since near-synonyms are already merged by CANONICAL_GROUPS -- once
# that's done, only the couple of strongest genuinely distinct sounds matter;
# a 3rd/4th slot mostly just adds low-confidence noise (stray "Vehicle",
# "Basketball bounce", etc.) rather than a meaningfully different sound.
MAX_DETECTIONS = 2

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

AMBIENT_GRACE_SECONDS = 1.5

# YAMNet's ontology has many overlapping/near-synonymous labels for the same
# real-world sound (a passing car can flicker between "Vehicle", "Motor
# vehicle (road)", and "Car" hop to hop; distant nature ambience flickers
# between "Insect", "Cricket", "Outside, rural or natural", "Wild animals").
CANONICAL_GROUPS: Dict[str, List[str]] = {
    "vehicle": [
        "Vehicle", "Motor vehicle (road)", "Car", "Truck", "Bus", "Motorcycle",
        "Traffic noise, roadway noise", "Race car, auto racing", "Skateboard",
    ],
    "speech": [
        "Speech", "Child speech, kid speaking", "Conversation",
        "Narration, monologue", "Babbling", "Shout", "Whispering",
    ],
    "insect_ambience": [
        "Insect", "Cricket", "Outside, rural or natural", "Wild animals", "Animal",
    ],
    "footsteps": ["Walk, footsteps", "Run", "Clip-clop", "Horse", "Gallop"],
    "gunfire": ["Gunshot, gunfire", "Machine gun", "Fusillade", "Explosion", "Artillery fire", 
            "Fireworks", "Eruption", "Boom", "Crackle", "Fire",],
    "music": ["Music", "Percussion", "Piano", "Guitar", "Drum", "Singing"],
}

LABEL_TO_GROUP: Dict[str, str] = {
    label: group for group, labels in CANONICAL_GROUPS.items() for label in labels
}

# The label actually surfaced for a group must stay stable across hops, even
# though which raw synonym scores highest can flip hop to hop (e.g. "Gunshot,
# gunfire" one hop, "Fusillade" the next).
GROUP_DISPLAY_LABEL: Dict[str, str] = {
    group: labels[0] for group, labels in CANONICAL_GROUPS.items()
}


def canonical_key(label: str) -> str:
    # Labels with no known group are their own group of one, so they're never
    # merged with anything else.
    return LABEL_TO_GROUP.get(label, label)


# Groups that are always ambience, regardless of persistence or direction.
ALWAYS_AMBIENT_GROUPS: Set[str] = {"insect_ambience", "basketball bounce"}


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
        self._active_since: Dict[str, float] = {}  # canonical group -> monotonic time it became continuously active
        self._last_active_at: Dict[str, float] = {}  # canonical group -> monotonic time last seen above MIN_CONFIDENCE
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
        # Persistence is tracked per canonical group rather than per exact label,
        # so a sound that flickers between near-synonyms (e.g. "Insect" one hop,
        # "Cricket" the next) still accumulates one continuous streak instead of
        # each synonym separately resetting the other's clock.
        active_groups = {canonical_key(self._class_names[idx]) for idx in above_threshold}

        # Start/stop the continuous-activity clock for each group so persistent
        # background sound (ambience) can be told apart from discrete events.
        # A brief dip below MIN_CONFIDENCE doesn't reset the streak -- only a
        # gap longer than AMBIENT_GRACE_SECONDS does -- so naturally noisy but
        # genuinely continuous ambience (crickets, wind) still accumulates.
        for group in active_groups:
            if group not in self._active_since:
                self._active_since[group] = now
            self._last_active_at[group] = now
        for group in list(self._active_since):
            if group not in active_groups and now - self._last_active_at[group] > AMBIENT_GRACE_SECONDS:
                del self._active_since[group]
                del self._last_active_at[group]

        detections: List[SoundDetection] = []
        detection_groups: List[str] = []  # parallel to `detections`, for leader matching below
        seen_groups: Set[str] = set()
        for idx in order:
            confidence = float(self._smoothed_scores[idx])
            if confidence < MIN_CONFIDENCE:
                break
            label = self._class_names[idx]
            group = canonical_key(label)
            # Only the strongest label per canonical group is surfaced each hop,
            # so near-synonyms (Vehicle/Motor vehicle (road)/Car, ...) don't show
            # up as separate simultaneous detections for the same real sound.
            if group in seen_groups:
                continue
            seen_groups.add(group)
            active_seconds = now - self._active_since[group]
            is_ambient = group in ALWAYS_AMBIENT_GROUPS or active_seconds >= AMBIENT_PERSISTENCE_SECONDS
            # Always surface the group's fixed display label, not whichever raw
            # synonym happened to win this hop -- see GROUP_DISPLAY_LABEL.
            display_label = GROUP_DISPLAY_LABEL.get(group, label)
            detections.append(SoundDetection(
                label=display_label,
                confidence=confidence,
                active_seconds=active_seconds,
                is_ambient=is_ambient,
            ))
            detection_groups.append(group)
            if len(detections) >= MAX_DETECTIONS:
                break

        leader_group = canonical_key(self._class_names[self._sticky_leader_idx])
        for i, group in enumerate(detection_groups):
            if group == leader_group and i != 0:
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