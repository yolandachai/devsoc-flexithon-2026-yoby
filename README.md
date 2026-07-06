# Auricle

## Highlights

- Real-time overlay displaying the direction of any given sound, driven by live WASAPI loopback capture of whatever game audio is playing on Windows, no in-game integration required.
- AI integrated multi-label sound classification (YAMNet) surfaces *what* is making noise (e.g. "Footsteps", "Insect", "Gunshot") alongside *where* it's coming from, with per-band direction so simultaneous sounds can point in different directions.
- Built as an Electron overlay so it sits on top of any game window.

## Overview

*Auricle* was created as a project for UNSW *DevSoc*'s 2026 Hackathon, 'Flexithon', which spanned the dates 03/07/2026–06/07/2026 and had the theme of 'Accessibility'.

*Auricle* was named for the visible part of the ear (also called the auricle) and because it sounds like oracle, and oracles are cool. *Auricle* aims to provide an overlayed interface that visualises the volume and direction of sound in a video game that is open, relative to the direction that your player character is facing.


### Authors

Authored by Toben1010 (https://github.com/toben1010) and Yolanda Chai (https://github.com/yolandachai).


## Usage

1. Start the backend (WASAPI capture, direction estimation, and classification pipeline) — see `backend/README.md` for full details.
2. Launch the Electron overlay from `frontend/`. It listens for the backend's output and renders the direction/volume overlay on top of your active game window.
3. Play as normal.

Windows only (WASAPI loopback capture is Windows specific).

## Installation

**Backend** (Python):

```
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

`tensorflow`/`tensorflow_hub` are large downloads and the first classification triggers a one-time ~15MB YAMNet download, see `backend/README.md` for troubleshooting.

**Frontend** (Electron overlay):

```
cd frontend
npm install
npm start
```

## Feedback and Contributing

This was built in ~72 hours for a hackathon, so expect rough edges. Issues and pull requests are welcome, see the module notes in `backend/README.md` for known limitations (e.g. self-noise filtering is implemented but not yet wired in).

