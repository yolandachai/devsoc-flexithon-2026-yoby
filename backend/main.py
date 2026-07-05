"""
main.py

Single entry point wiring the currently-implemented pipeline stages together

self_noise_filter.py is implemented but parked out of this pipeline for
now

Windows only.
"""

import sys
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


def process_block(
    levels: List[float],
    labels: List[str],
    raw_block: np.ndarray,
    audio_buffer: RollingAudioBuffer,
    classifier: YamNetClassifier,
    band_estimator: BandDirectionEstimator,
) -> Tuple[DirectionEstimate, Optional[ClassificationResult], Optional[BandDirections]]:
    # Estimate direction from the current RMS levels, classify the current audio window if 
    # enough audio has accumulated, and estimate band directions if a window is available.
    direction = estimate_direction(levels, labels)

    classification = None
    band_directions = None
    window = audio_buffer.add_block(raw_block)
    if window is not None:
        classification = classifier.classify_native_rate(window, audio_buffer.sample_rate)
        band_directions = band_estimator.estimate(window, labels, audio_buffer.sample_rate)

    return direction, classification, band_directions


def main() -> None:
    p = pyaudio.PyAudio()
    classifier = YamNetClassifier()
    band_estimator = BandDirectionEstimator()
    last_classification: Optional[ClassificationResult] = None
    last_band_directions: Optional[BandDirections] = None

    try:
        devices = list_loopback_devices(p)
        if not devices:
            sys.exit(1)

        device = choose_device(devices)
        channels = int(device["maxInputChannels"])
        sample_rate = int(device["defaultSampleRate"])
        labels = channel_labels_for(channels)
        audio_buffer = RollingAudioBuffer(sample_rate=sample_rate, channels=channels)

        print(f"\nCapturing from: {device['name']}")
        print(f"Channels: {channels}  |  Sample rate: {sample_rate} Hz")
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

                direction, classification, band_directions = process_block(
                    levels, labels, audio, audio_buffer, classifier, band_estimator
                )
                if classification is not None:
                    last_classification = classification
                if band_directions is not None:
                    last_band_directions = band_directions

                bars = "  ".join(
                    f"{label}:{level_bar(db)}"
                    for label, db in zip(labels, levels_db)
                )
                direction_str = (
                    f"{direction.label} ({direction.confidence:.2f})"
                    if direction.available
                    else direction.label
                )

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

                # server.py not implemented yet.

        except KeyboardInterrupt:
            print("\nStopping...")

        finally:
            stream.stop_stream()
            stream.close()

    finally:
        p.terminate()


if __name__ == "__main__":
    main()