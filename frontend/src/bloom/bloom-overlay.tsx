import { createRoot } from 'react-dom/client';
import './bloom-overlay.css';
import { useEffect, useRef, useState } from 'react';
import { subscribeToEvents } from '../server/api';
import { dataForBloom } from './sound-direction-to-bloom';

const SMOOTHING = 0.25;
const IDLE_TIMER = 1500; // in ms
const MIN_RADIUS = 130; // px, resting size of the semi-circle
const MAX_RADIUS = 420; // px, size at full intensity

interface TrackedSound {
  side: 'left' | 'right';
  intensity: number;
  text: string;
  updatedAt: number;
}

function BloomOverlay() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuOpenRef = useRef(false);

  // Tracks every sound heard recently, keyed by label, so the loudest one on
  // each side can be picked even if it wasn't the very last event received.
  const soundsRef = useRef<Record<string, TrackedSound>>({});
  const drawnRef = useRef({ left: 0, right: 0 });

  const leftShapeRef = useRef<HTMLDivElement>(null);
  const rightShapeRef = useRef<HTMLDivElement>(null);
  const leftLabelRef = useRef<HTMLDivElement>(null);
  const rightLabelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    window.overlayApi.onMenuOpenChanged((isOpen) => {
      menuOpenRef.current = isOpen;
      setMenuOpen(isOpen);
    });
  }, []);

  useEffect(() => {
    return subscribeToEvents((event) => {
      const target = dataForBloom(event.direction, event.confidence);
      if (!target.dataAvailable || !target.side) return;
      soundsRef.current[event.label || 'sound'] = {
        side: target.side,
        intensity: target.intensity,
        text: `${event.label || 'Sound'} — ${event.direction.label}`,
        updatedAt: performance.now(),
      };
    });
  }, []);

  // animate responsive bloom shapes
  useEffect(() => {
    let frame: number;

    const tick = () => {
      const now = performance.now();
      const sounds = soundsRef.current;
      for (const label of Object.keys(sounds)) {
        if (now - sounds[label].updatedAt > IDLE_TIMER) delete sounds[label];
      }

      const loudest = (side: 'left' | 'right') =>
        Object.values(sounds)
          .filter((s) => s.side === side)
          .sort((a, b) => b.intensity - a.intensity)[0];

      const leftSound = loudest('left');
      const rightSound = loudest('right');

      const drawn = drawnRef.current;
      drawn.left += ((leftSound?.intensity ?? 0) - drawn.left) * SMOOTHING;
      drawn.right += ((rightSound?.intensity ?? 0) - drawn.right) * SMOOTHING;

      applyBloomSize(leftShapeRef.current, drawn.left);
      applyBloomSize(rightShapeRef.current, drawn.right);

      setLabel(leftLabelRef.current, leftSound?.text ?? '');
      setLabel(rightLabelRef.current, rightSound?.text ?? '');

      frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  const handleControlsMouseEnter = () => {
    if (!menuOpenRef.current) window.overlayApi.setIgnoreMouseEvents(false);
  };
  const handleControlsMouseLeave = () => {
    if (!menuOpenRef.current) window.overlayApi.setIgnoreMouseEvents(true);
  };

  return (
    <div className="bloom-container">
      <div ref={leftShapeRef} className="bloom-shape bloom-shape-left" />
      <div ref={rightShapeRef} className="bloom-shape bloom-shape-right" />

      <div ref={leftLabelRef} className="bloom-label bloom-label-left" />
      <div ref={rightLabelRef} className="bloom-label bloom-label-right" />

      <div
        className="bloom-controls"
        onMouseEnter={handleControlsMouseEnter}
        onMouseLeave={handleControlsMouseLeave}
      >
        <button
          className="bloom-btn"
          disabled={menuOpen}
          onClick={() => {
            if (menuOpenRef.current) return;
            window.overlayApi.focusMenu();
            window.overlayApi.closeOverlay('bloom');
          }}
        >
          Menu
        </button>
        <button
          className="bloom-btn bloom-btn-close"
          disabled={menuOpen}
          onClick={() => { if (!menuOpenRef.current) window.overlayApi.closeOverlay('bloom'); }}
        >
          Close
        </button>
      </div>
    </div>
  );
}

/**
 * Sizes a bloom semi-circle based on intensity (0-1), keeping it centered
 * on the screen edge so it grows/shrinks inward as a semi-circle.
 */
function applyBloomSize(el: HTMLDivElement | null, intensity: number) {
  if (!el) return;
  const radius = MIN_RADIUS + (MAX_RADIUS - MIN_RADIUS) * intensity;
  el.style.width = `${radius * 2}px`;
  el.style.opacity = `${0.5 + 0.5 * intensity}`;
}

function setLabel(el: HTMLDivElement | null, text: string) {
  if (!el) return;
  el.textContent = text;
  el.classList.toggle('bloom-label-visible', text !== '');
}

const root = createRoot(document.getElementById('root')!);
root.render(<BloomOverlay />);
