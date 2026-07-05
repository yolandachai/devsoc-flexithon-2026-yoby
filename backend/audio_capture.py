"""
audio_capture.py

Captures system/game audio via WASAPI loopback and prints live per-channel
RMS levels to the console.

Windows only (PyAudioWPatch wraps WASAPI, which is Windows-specific).

Usage:
    python audio_capture.py
"""

import sys

import numpy as np
import pyaudiowpatch as pyaudio

from direction import estimate_direction

CHUNK_SIZE = 1024  # frames read per loop iteration

# Typical channel order for an 8-channel (7.1) WASAPI device. Driver
# implementations vary, so treat this as a default rather than a guarantee.
CHANNEL_LABELS_8 = [
    "Front-L", "Front-R", "Center", "LFE",
    "Rear-L", "Rear-R", "Side-L", "Side-R",
]
CHANNEL_LABELS_2 = ["Left", "Right"]

"""Return all available WASAPI loopback devices, printing them for selection."""
def list_loopback_devices(p: "pyaudio.PyAudio") -> list:
    print("Available loopback devices:")
    devices = []
    for loopback in p.get_loopback_device_info_generator():
        devices.append(loopback)
        print(
            f"  [{len(devices) - 1}] {loopback['name']} "
            f"({int(loopback['maxInputChannels'])} channels, "
            f"{int(loopback['defaultSampleRate'])} Hz)"
        )
    if not devices:
        print("No loopback devices found.")
    return devices

"""Prompt for device selection, or auto-select if there's only one option."""
def choose_device(devices: list) -> dict:
    if len(devices) == 1:
        print("\nOnly one loopback device found, using it automatically.")
        return devices[0]

    while True:
        choice = input(f"\nSelect a device [0-{len(devices) - 1}]: ").strip()
        if choice.isdigit() and 0 <= int(choice) < len(devices):
            return devices[int(choice)]
        print("Invalid choice, try again.")

"""
Compute RMS energy per channel for a block of interleaved int16 audio.

audio_block shape: (frames, channels)
Returns: 1D array of RMS values, one per channel.
"""
def rms_per_channel(audio_block: np.ndarray) -> np.ndarray:
    float_block = audio_block.astype(np.float32)
    return np.sqrt(np.mean(float_block ** 2, axis=0))

"""
Convert linear RMS (int16 scale) to dBFS (decibels relative to full scale).

0 dBFS = full-scale amplitude (clipping). Silence maps to floor_db
rather than -inf, so the bar renderer has a defined lower bound.
"""
def rms_to_dbfs(rms: float, full_scale: float = 32768.0, floor_db: float = -60.0) -> float:
    if rms <= 0:
        return floor_db
    db = 20 * np.log10(rms / full_scale)
    return max(db, floor_db)

"""Render a dBFS value as an ASCII bar."""
def level_bar(dbfs: float, min_db: float = -60.0, max_db: float = 0.0, width: int = 25) -> str:
    fraction = (dbfs - min_db) / (max_db - min_db)
    fraction = min(max(fraction, 0.0), 1.0)
    filled = int(fraction * width)
    return "#" * filled + "-" * (width - filled)

def channel_labels_for(channels: int) -> list:
    if channels == 2:
        return CHANNEL_LABELS_2
    if channels == 8:
        return CHANNEL_LABELS_8
    return [f"Ch{i}" for i in range(channels)]
