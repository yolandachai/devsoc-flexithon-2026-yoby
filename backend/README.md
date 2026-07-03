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

- `audio_capture.py` — WASAPI loopback capture, per-channel level reporting.

## Running

Currently `audio_capture.py` is the only runnable module:

```
python audio_capture.py
```

Lists available WASAPI loopback devices, then prints live per-channel RMS
levels as ASCII bars:

```
Front-L:#######--------------  Front-R:###------------------
Center:-------------------------  LFE:-------------------------
```

Once `main.py` exists, it will be the single entry point for the full
pipeline and WebSocket server.

## Notes

- A device reporting 2 channels caps directional resolution to
  left/right, regardless of how a game mixes audio internally.
  Routing output through a virtual multichannel device (e.g. Voicemeeter
  Banana configured for 7.1) can expose true surround data if the
  physical device doesn't.
- `exception_on_overflow=False` prevents crashes on dropped frames;
  frequent drops indicate `CHUNK_SIZE` may need tuning.
- Channel label order (`CHANNEL_LABELS_8`) is a default assumption for
  8-channel devices, not guaranteed, verify against actual panning.