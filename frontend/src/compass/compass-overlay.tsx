import { createRoot } from 'react-dom/client';
import { useEffect, useRef, useState } from 'react';
import './compass-overlay.css';

/** Matches the wire format documented in backend/server.py. */
interface DirectionWire {
  available: boolean;
  mode: 'stereo' | 'multichannel' | 'none';
  pan: number | null;
  azimuth_deg: number | null;
  label: string;
}

interface SoundWire {
  label: string;
  confidence: number;
  direction: DirectionWire;
  timestamp: number;
}

interface TrackedSound extends SoundWire {
  updatedAt: number;
}

const SERVER_URL = 'ws://localhost:8765';
// How long a sound stays on the compass after its last update.
const STALE_MS = 4000;
// Sounds within this many degrees of each other are treated as "the same
// spot" for label stacking purposes.
const STACK_BUCKET_DEG = 15;

// The strip only covers the front hemisphere (-90 = left ... 90 = right).
// Stereo pan can't distinguish front from back at all, so a full 360-degree
// compass just adds dead/misleading zones -- this keeps it to the range
// that's actually meaningful on a stereo setup.
const DISPLAY_RANGE_DEG = 90;

// Tick marks drawn along the strip, independent of any live sound. No text
// labels -- position alone conveys left/right/center.
const TICKS: number[] = [-90, -45, 0, 45, 90];

// Stereo direction only carries left/right pan, so it's mapped onto the
// front hemisphere of the compass rather than claiming a false front/back
// position.
function toAzimuth(direction: DirectionWire): number | null {
  if (!direction.available) return null;
  if (direction.mode === 'multichannel' && direction.azimuth_deg !== null) {
    return direction.azimuth_deg;
  }
  if (direction.mode === 'stereo' && direction.pan !== null) {
    return direction.pan * 90;
  }
  return null;
}

function clampAzimuth(deg: number): number {
  return Math.max(-DISPLAY_RANGE_DEG, Math.min(DISPLAY_RANGE_DEG, deg));
}

function azimuthToPercent(deg: number): number {
  return 50 + (clampAzimuth(deg) / DISPLAY_RANGE_DEG) * 50;
}

function CompassOverlay() {
  const [sounds, setSounds] = useState<Record<string, TrackedSound>>({});
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;

    const connect = () => {
      const socket = new WebSocket(SERVER_URL);
      socketRef.current = socket;

      socket.onmessage = (message) => {
        const event: SoundWire = JSON.parse(message.data);
        setSounds((prev) => ({
          ...prev,
          [event.label]: { ...event, updatedAt: Date.now() },
        }));
      };

      socket.onclose = () => {
        if (!cancelled) setTimeout(connect, 1000);
      };
    };

    connect();
    return () => {
      cancelled = true;
      socketRef.current?.close();
    };
  }, []);

  // Periodically drop sounds that haven't been re-heard recently.
  useEffect(() => {
    const interval = setInterval(() => {
      setSounds((prev) => {
        const now = Date.now();
        const next: Record<string, TrackedSound> = {};
        for (const [label, sound] of Object.entries(prev)) {
          if (now - sound.updatedAt <= STALE_MS) next[label] = sound;
        }
        return next;
      });
    }, 500);
    return () => clearInterval(interval);
  }, []);

  const markers = Object.values(sounds)
    .map((sound) => ({ sound, azimuth: toAzimuth(sound.direction) }))
    .filter((m): m is { sound: TrackedSound; azimuth: number } => m.azimuth !== null)
    .sort((a, b) => clampAzimuth(a.azimuth) - clampAzimuth(b.azimuth));

  // Assign a stacking slot (0 = label above the pin, 1 = label below) to
  // markers that land on roughly the same bearing.
  const stackSlotByLabel: Record<string, number> = {};
  let lastBucket: number | null = null;
  let slot = 0;
  for (const { sound, azimuth } of markers) {
    const bucket = Math.round(clampAzimuth(azimuth) / STACK_BUCKET_DEG);
    slot = bucket === lastBucket ? slot + 1 : 0;
    lastBucket = bucket;
    stackSlotByLabel[sound.label] = slot % 2;
  }

  return (
    <div className="compass-root">
      <div className="compass-strip">
        {TICKS.map((deg) => (
          <div
            key={deg}
            className="compass-tick"
            style={{ left: `${azimuthToPercent(deg)}%` }}
          >
            <span className="compass-tick-mark" />
          </div>
        ))}

        <div className="compass-center-marker" />

        {markers.map(({ sound, azimuth }) => {
          const confidence = Math.max(0, Math.min(1, sound.confidence));
          const opacity = 0.4 + confidence * 0.6;
          const scale = 0.8 + confidence * 0.5;
          const below = stackSlotByLabel[sound.label] === 1;

          return (
            <div
              key={sound.label}
              className={`compass-marker ${below ? 'label-below' : 'label-above'}`}
              style={{
                left: `${azimuthToPercent(azimuth)}%`,
                opacity,
                transform: `translateX(-50%) scale(${scale})`,
              }}
            >
              <span className="compass-marker-label">{sound.label}</span>
              <span className="compass-marker-pin" />
            </div>
          );
        })}
      </div>
    </div>
  );
}

const root = createRoot(document.getElementById('root')!);
root.render(<CompassOverlay />);
