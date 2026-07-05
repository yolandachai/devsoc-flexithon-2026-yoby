# Backend

Python backend: WASAPI loopback audio capture, direction estimation, sound
classification, and WebSocket broadcast to the overlay UI.

Windows only.

## Setup

```
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Modules

- `audio_capture.py` — WASAPI loopback capture, per-channel level
  reporting, live console meter.
- `direction.py` — converts per-channel levels into a direction estimate
  (stereo pan or multichannel azimuth) with a confidence score.

## Running

Currently `audio_capture.py` is the only runnable module:

```
python audio_capture.py
```

Lists available WASAPI loopback devices, then prints a live per-channel
ASCII level meter plus a live direction estimate:

```
Front-L:#######--------------  Front-R:###------------------
Center:-------------------------  LFE:-------------------------
   |  Direction: front-left (confidence 0.62)
```

`direction.py` also has a standalone synthetic self-test (no audio
hardware required):

```
python direction.py
```

Once `main.py` exists, it will be the single entry point for the full
pipeline and WebSocket server.

## Direction estimation

- **Stereo (2ch):** pan from -1.0 (left) to +1.0 (right), derived from
  L/R energy difference. Confidence scales with `abs(pan)` — near 0 means
  audible on both sides (ambiguous direction), near 1 means strongly
  localized to one side. Stereo can only represent left/right balance, not
  front/back or elevation.
- **Multichannel (8ch, 7.1 layout):** azimuth in degrees via a weighted
  vector sum of channel energies at fixed speaker angles. Confidence is
  the vector magnitude relative to total energy, near 0 means diffuse/
  ambient sound (energy spread evenly across channels), near 1 means a
  clear point source. LFE is excluded (no directional meaning).
- **Anything else** (mono, unsupported channel counts, or total energy
  below the silence threshold): no direction is claimed
  (`available=False`), and the overlay is expected to fall back to
  subtitle-only display.

## Notes

- A device reporting 2 channels caps directional resolution to
  left/right, regardless of how a game mixes audio internally. Routing
  output through a virtual multichannel device (e.g. Voicemeeter Banana
  configured for 7.1) can expose true surround data if the physical
  device doesn't.
- Stereo mixes represent center as balanced L/R energy rather than a
  discrete channel, a stereo device reporting Left/Right only (no
  Center) is expected behavior, not a bug. True Center/LFE/rear/side
  channels require an 8-channel device.
- Level meters use dBFS scaling (-60dB floor to 0dB = full scale),
  matching standard audio meter conventions, rather than raw linear RMS,
  int16 RMS values routinely exceed a fixed linear reference well below
  actual clipping, which pins the bar near full at any normal listening
  volume.
- The live console line is redrawn with `\r` plus the ANSI "clear to end
  of line" code (`\033[K`), so shorter lines don't leave stray characters
  from a longer previous line. Assumes a terminal with ANSI escape
  support (Windows Terminal/PowerShell — fine; plain `cmd.exe` may not
  honor it).
- `exception_on_overflow=False` prevents crashes on dropped frames;
  frequent drops indicate `CHUNK_SIZE` may need tuning.
- Channel label order (`CHANNEL_LABELS_8` / `CHANNEL_ANGLES_8`) is a
  default assumption for 8-channel devices, not guaranteed, verify
  against actual panning, since driver implementations vary.