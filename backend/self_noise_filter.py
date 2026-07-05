"""
self_noise_filter.py

Suppresses sounds caused by the player's own actions (footsteps, gunshots,
reload clicks, etc.) so the overlay only surfaces subtitles for other
players and environmental audio.

Currently not working and disabled by default as the loud+uniform heuristic is too aggressive 
and the input hook is too unreliable to be useful in practice. The
loud+uniform heuristic
"""

import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Deque, List, Optional, Set

# --- Adaptive noise floor tuning -----------------------------------------

FLOOR_ADAPT_RATE = 0.003

FLOOR_ADAPT_CEILING_MULTIPLE = 3.0

LOUD_CEILING_MULTIPLE = 6.0

MIN_FLOOR = 1.0 

# --- Channel uniformity tuning --------------------------------------------

UNIFORMITY_THRESHOLD = 0.65

# --- Input timing tuning -------------------------------------------------

INPUT_CORRELATION_WINDOW_S = 0.20

DEFAULT_MOVEMENT_KEYS: Set[str] = {"w", "a", "s", "d"}

# --- Combination tuning ---------------------------------------------------

AUDIO_WEIGHT = 0.4
TIMING_WEIGHT = 0.6
SUPPRESSION_THRESHOLD = 0.6


@dataclass
class SelfNoiseResult:
    suppressed: bool      # True if this block should be treated as self-noise
    score: float           # combined suppression score
    audio_score: float     # loud+uniform 
    timing_score: float    # input correlation
    reason: str            # human readable explanation, for debugging/tuning


class NoiseFloorTracker:
    """ Tracks the adaptive ambient noise floor per channel, so we can tell
    when a block of audio is "loud" relative to the current ambient level."""

    def __init__(self, num_channels: int, adapt_rate: float = FLOOR_ADAPT_RATE):
        self.floor = [MIN_FLOOR] * num_channels
        self.adapt_rate = adapt_rate
        self._initialized = False

    def update(self, levels: List[float]) -> None:
        if not self._initialized:
            self.floor = [max(level, MIN_FLOOR) for level in levels]
            self._initialized = True
            return

        for i, level in enumerate(levels):
            if i >= len(self.floor):
                break
            if level < self.floor[i] * FLOOR_ADAPT_CEILING_MULTIPLE:
                self.floor[i] = (
                    self.floor[i] * (1 - self.adapt_rate) + level * self.adapt_rate
                )
            self.floor[i] = max(self.floor[i], MIN_FLOOR)

    def loud_fraction(self, levels: List[float]) -> float:
        total_floor = sum(self.floor[: len(levels)])
        total = sum(levels)
        if total_floor <= 0:
            return 0.0
        ratio = total / total_floor
        fraction = (ratio - 1.0) / (LOUD_CEILING_MULTIPLE - 1.0)
        return max(0.0, min(1.0, fraction))


class InputEventMonitor:
    # Tracks recent keyboard/mouse activity via a global input hook (pynput)

    def __init__(
        self,
        movement_keys: Set[str] = None,
        window_s: float = INPUT_CORRELATION_WINDOW_S,
    ):
        self.movement_keys = movement_keys or set(DEFAULT_MOVEMENT_KEYS)
        self.window_s = window_s
        self._lock = Lock()
        self._events: Deque[float] = deque(maxlen=64)
        self._listeners = []
        self._available = False

    def start(self) -> bool:
        # Attempt to start the global input hook. Returns whether it succeeded.
        try:
            from pynput import keyboard, mouse
        except ImportError:
            self._available = False
            return False

        def on_press(key):
            name = _key_name(key)
            if name in self.movement_keys:
                self._record()

        def on_click(x, y, button, pressed):
            if pressed:
                self._record()

        try:
            kb_listener = keyboard.Listener(on_press=on_press)
            mouse_listener = mouse.Listener(on_click=on_click)
            kb_listener.start()
            mouse_listener.start()
            self._listeners = [kb_listener, mouse_listener]
            self._available = True
            return True
        except Exception:
            self._available = False
            return False

    def stop(self) -> None:
        for listener in self._listeners:
            listener.stop()
        self._listeners = []
        self._available = False

    def _record(self) -> None:
        with self._lock:
            self._events.append(time.monotonic())

    def recent_input_score(self, now: Optional[float] = None) -> float:
        """
        0.0-1.0: 1.0 if a relevant input event happened right now, decaying
        linearly to 0.0 at the edge of the correlation window. Returns 0.0
        if the hook isn't available (no signal, not "no input").
        """
        if not self._available:
            return 0.0

        now = now if now is not None else time.monotonic()
        with self._lock:
            if not self._events:
                return 0.0
            most_recent = self._events[-1]

        age = now - most_recent
        if age < 0 or age > self.window_s:
            return 0.0
        return 1.0 - (age / self.window_s)

    @property
    def available(self) -> bool:
        return self._available


def _key_name(key) -> Optional[str]:
    # Normalize a pynput key object down to a lowercase character, if any.
    return getattr(key, "char", None) and key.char.lower()


def _uniformity_fraction(levels: List[float]) -> float:
    total = sum(levels)
    if total <= 0:
        return 0.0
    floor = min(levels)
    residual = total - floor * len(levels)
    return max(0.0, min(1.0, 1.0 - (residual / total)))


def _audio_component(levels: List[float], floor_tracker: NoiseFloorTracker) -> tuple:
    # Returns (audio_score, is_loud, is_centered) for the loud+uniform heuristic.
    loud_fraction = floor_tracker.loud_fraction(levels)
    is_loud = loud_fraction > 0.5

    uniformity = _uniformity_fraction(levels)
    is_centered = uniformity >= UNIFORMITY_THRESHOLD

    audio_score = 0.7 * loud_fraction + 0.3 * uniformity
    return audio_score, is_loud, is_centered


def estimate_self_noise(
    levels: List[float],
    floor_tracker: NoiseFloorTracker,
    monitor: InputEventMonitor,
    now: Optional[float] = None,
) -> SelfNoiseResult:
    # Estimate whether the current block of audio is likely to be self-noise
    audio_score, is_loud, is_centered = _audio_component(levels, floor_tracker)
    timing_score = monitor.recent_input_score(now)

    score = AUDIO_WEIGHT * audio_score + TIMING_WEIGHT * timing_score
    suppressed = score >= SUPPRESSION_THRESHOLD

    if not monitor.available and is_loud and is_centered:
        reason = "loud+uniform, no input hook available (audio-only signal)"
    else:
        reason = (
            f"loud={is_loud} uniform={is_centered} "
            f"input_correlated={timing_score > 0.0}"
        )

    return SelfNoiseResult(
        suppressed=suppressed,
        score=score,
        audio_score=audio_score,
        timing_score=timing_score,
        reason=reason,
    )