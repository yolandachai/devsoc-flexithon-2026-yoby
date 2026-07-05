"""
main.py

Single entry point wiring the full pipeline together:

    WASAPI loopback capture (audio_capture.py)
            |
    Direction estimate (direction.py)
            |
    Sound classification (classifier.py)
            |
    Per-band direction (band_direction.py)
            |
    WebSocket broadcast (server.py)

Windows only.
"""

import queue
import sys
import threading
from typing import List, Optional, Tuple

import numpy as np
import pyaudiowpatch as pyaudio

from audio_capture import (
    CHUNK_SIZE,
    channel_labels_for,
    choose_device,
    level_bar,
    list_loopback_devices,
    rms_per_channel,
    rms_to_dbfs,
)
from band_direction import BandDirectionEstimator, BandDirections
from classifier import ClassificationResult, RollingAudioBuffer, YamNetClassifier
from direction import DirectionEstimate, estimate_direction
from server import SubtitleServer, build_event


def process_block(
    levels: List[float],
    labels: List[str],
    raw_block: np.ndarray,
    audio_buffer: RollingAudioBuffer,
) -> Tuple[DirectionEstimate, Optional[np.ndarray]]:
    # Process a single block of audio: estimate direction (cheap, runs every block)
    # and hand off a window for classification when one becomes available. The
    # window itself is NOT classified here -- that happens on a background
    # thread so slow YAMNet inference never blocks audio capture.
    direction = estimate_direction(levels, labels)
    window = audio_buffer.add_block(raw_block)
    return direction, window


class ClassificationWorker:
    # Runs YAMNet classification + per-band direction estimation on a background
    # thread, decoupled from the audio capture loop. Only the most recent window
    # is kept -- if classification falls behind, older windows are dropped rather
    # than queued up, so results stay as close to real-time as possible.
    def __init__(
        self,
        classifier: YamNetClassifier,
        band_estimator: BandDirectionEstimator,
        labels: List[str],
        sample_rate: int,
        server: SubtitleServer,
    ):
        self._classifier = classifier
        self._band_estimator = band_estimator
        self._labels = labels
        self._sample_rate = sample_rate
        self._server = server
        self._queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=1)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.last_classification: Optional[ClassificationResult] = None
        self.last_band_directions: Optional[BandDirections] = None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=2.0)

    def submit(self, window: np.ndarray) -> None:
        # Drop the pending window (if any) in favor of the newest one, so the
        # worker is always processing the freshest audio available.
        try:
            self._queue.get_nowait()
        except queue.Empty:
            pass
        self._queue.put_nowait(window)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                window = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            classification = self._classifier.classify_native_rate(window, self._sample_rate)
            band_directions = self._band_estimator.estimate(window, self._labels, self._sample_rate)
            self.last_classification = classification
            self.last_band_directions = band_directions

            if classification.available:
                for d in classification.detections:
                    sound_dir = band_directions.for_label(d.label)
                    self._server.publish(build_event(d.label, d.confidence, sound_dir))


def main() -> None:
    p = pyaudio.PyAudio()
    classifier = YamNetClassifier()
    band_estimator = BandDirectionEstimator()
    server = SubtitleServer()
    server.start()
    worker: Optional[ClassificationWorker] = None

    try:
        devices = list_loopback_devices(p)
        if not devices:
            sys.exit(1)

        device = choose_device(devices)
        channels = int(device["maxInputChannels"])
        sample_rate = int(device["defaultSampleRate"])
        labels = channel_labels_for(channels)
        audio_buffer = RollingAudioBuffer(sample_rate=sample_rate, channels=channels)
        worker = ClassificationWorker(classifier, band_estimator, labels, sample_rate, server)
        worker.start()

        print(f"\nCapturing from: {device['name']}")
        print(f"Channels: {channels}  |  Sample rate: {sample_rate} Hz")
        print(f"Overlay connects to: ws://{server.host}:{server.port}")
        print("Loading YAMNet on first classification (downloads on first run)...")
        print("Press Ctrl+C to stop.\n")

        stream = p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            input=True,
            input_device_index=device["index"],
            frames_per_buffer=CHUNK_SIZE,
        )

        try:
            while True:
                raw = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                audio = np.frombuffer(raw, dtype=np.int16).reshape(-1, channels)
                levels = list(rms_per_channel(audio))
                levels_db = [rms_to_dbfs(lvl) for lvl in levels]

                direction, window = process_block(levels, labels, audio, audio_buffer)
                if window is not None:
                    worker.submit(window)

                bars = "  ".join(
                    f"{label}:{level_bar(db)}"
                    for label, db in zip(labels, levels_db)
                )
                direction_str = (
                    f"{direction.label} ({direction.confidence:.2f})"
                    if direction.available
                    else direction.label
                )

                last_classification = worker.last_classification
                last_band_directions = worker.last_band_directions
                if last_classification is not None and last_classification.available:
                    parts = []
                    for d in last_classification.detections:
                        if last_band_directions is not None:
                            sound_dir = last_band_directions.for_label(d.label)
                            dir_str = sound_dir.label if sound_dir.available else "?"
                        else:
                            dir_str = "?"
                        parts.append(f"{d.label} ({d.confidence:.2f}) @ {dir_str}")
                    sound_str = " | ".join(parts)
                else:
                    sound_str = "..."

                print(
                    f"\r{bars}   |  Dir: {direction_str}   |  Sound: {sound_str}\033[K",
                    end="",
                    flush=True,
                )

        except KeyboardInterrupt:
            print("\nStopping...")

        finally:
            stream.stop_stream()
            stream.close()

    finally:
        if worker is not None:
            worker.stop()
        server.stop()
        p.terminate()


if __name__ == "__main__":
    main()