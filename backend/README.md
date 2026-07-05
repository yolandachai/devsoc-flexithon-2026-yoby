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

`tensorflow`/`tensorflow_hub` are large downloads (used by `classifier.py`)
— the install will take a while. See **Troubleshooting** below if it
fails partway through, the failure modes actually hit are documented
there rather than guessed at.

## Modules

- `audio_capture.py` - WASAPI loopback capture, per-channel level
  reporting, live console meter.
- `direction.py` - converts per-channel levels into a broadband direction
  estimate (stereo pan or multichannel azimuth) with a confidence score.
- `classifier.py` - wraps YAMNet to classify ~1-second audio windows into
  one or more simultaneous sound labels (e.g. "Insect", "Footsteps") with
  confidence, using score smoothing to keep the displayed
  label stable instead of flickering between tied classes.
- `band_direction.py` - splits each classification window into 5
  frequency bands and estimates direction independently per band, then
  attributes each classified sound to the band it's typically associated
  with. This is what lets two simultaneous sounds (e.g. a footstep and an
  insect chirp) get two different directions instead of one blended
  guess (this is **not** true separation however, see below).
- `self_noise_filter.py` - implemented (loudness + channel-uniformity +
  input-timing heuristics to suppress the player's own footsteps/etc.),
  but currently **not wired into `main.py`**. Parked until it can be
  gated by a classifier label instead of relying on heuristics alone —
  see the module's own docstring for the reasoning and prior tuning
  history.
- `main.py` - single entry point. Wires WASAPI capture → broadband
  direction (every block) → classification + per-band direction (every
  ~0.5s window) → console output.
- `server.py` - not yet implemented. Will be a lightweight local WebSocket server broadcasting
  pipeline output as JSON events for the overlay UI to consume.

## Running

```
python main.py
```

Lists available WASAPI loopback devices, then prints a live view:

```
Left:#######------------------  Right:#######------------------   |  Dir: center (0.10)   |  Sound: Insect (0.62) @ left | Footsteps (0.31) @ right
```

- `Dir:` is the fast, broadband direction, updates every audio block,
  reflects the whole mixed signal.
- `Sound:` lists every currently detected sound (YAMNet is multi-label,
  so more than one can be showing at once) with its own per-band
  attributed direction, updating roughly every 0.5s (classification needs
  more context than a single block).

First classification triggers a ~15MB YAMNet download from tfhub.dev
(needs internet once; cached afterward). Expect several seconds of
TensorFlow/tfhub startup logging (oneDNN, deprecated-API warnings from
tfhub's own internals, etc.) the first time a window gets classified,
this is normal and not an error, see Troubleshooting if you're unsure
whether something printed is actually a problem.

Individual modules also have their own standalone checks (no live audio
needed):

```
python direction.py       # synthetic stereo/multichannel direction cases
python band_direction.py  # synthetic low-tone-left + high-tone-right mix
python classifier.py      # classifies synthetic silence + white noise
```

## Direction estimation

**Broadband (`direction.py`):**
- **Stereo (2ch):** pan from -1.0 (left) to +1.0 (right), derived from
  L/R energy difference.
- **Multichannel (8ch, 7.1 layout):** azimuth in degrees via a weighted
  vector sum of channel energies at fixed speaker angles. Confidence is
  the vector magnitude relative to total energy — near 0 means diffuse/
  ambient sound (energy spread evenly across channels), near 1 means a
  clear point source. LFE is excluded (no directional meaning).
- **Anything else** (mono, unsupported channel counts, or total energy
  below the silence threshold): no direction is claimed
  (`available=False`), and the overlay is expected to fall back to
  subtitle-only display.

**Per-band (`band_direction.py`):** the same stereo/multichannel logic
above, run independently on 5 frequency bands (sub_low/low/mid/high/ultra)
instead of the whole signal at once. `BandDirections.for_label()` maps a
classified sound to its band via a coarse, hand-written lookup
(`LABEL_BAND_HINTS`) extends that table as real gameplay testing turns up
gaps.

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

## Troubleshooting

- **`pip install tensorflow` fails with "no matching distribution".**
  TensorFlow currently lags behind the latest Python releases (only
  up to ~3.12 as of writing). Check `python --version`, if it's newer
  than TensorFlow supports, create the venv with an older interpreter
  instead: `py -3.12 -m venv venv`.
- **`ModuleNotFoundError: No module named 'pkg_resources'`** when
  `tensorflow_hub` imports. `setuptools` v82+ removed `pkg_resources`
  entirely; `tensorflow_hub` still depends on it internally.
  `requirements.txt` pins `setuptools<82` for this reason, if it recurs,
  confirm that pin actually installed (`pip show setuptools`).