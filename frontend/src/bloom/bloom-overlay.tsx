import { createRoot } from 'react-dom/client';
import './bloom-overlay.css';
import { useEffect, useRef, useState } from 'react';
import { useLatestEvent } from '../server/api';
import { dataForBloom } from './sound-direction-to-bloom';

const SMOOTHING = 0.25;
const IDLE_TIMER = 1500; // in ms
const MIN_RADIUS = 130; // px, resting size of the semi-circle
const MAX_RADIUS = 420; // px, size at full intensity

function BloomOverlay() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuOpenRef = useRef(false);

  const [controlsVisible, setControlsVisible] = useState(false);
  const hoverTimerRef = useRef<number | null>(null);

  const latestEvent = useLatestEvent();

  const drawnRef = useRef({ left: 0, right: 0 });
  const lastEventAtRef = useRef<number>(0);

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

  const targetRef = useRef({ side: null as 'left' | 'right' | null, intensity: 0, dataAvailable: false });
  useEffect(() => {
    if (!latestEvent) return;
    const target = dataForBloom(latestEvent.direction, latestEvent.confidence);
    targetRef.current = target;
    lastEventAtRef.current = performance.now();

    const text = target.dataAvailable ? `${latestEvent.label || 'Sound'} — ${latestEvent.direction.label}` : '';
    if (leftLabelRef.current) {
      leftLabelRef.current.textContent = target.side === 'left' ? text : '';
      leftLabelRef.current.classList.toggle('bloom-label-visible', target.side === 'left');
    }
    if (rightLabelRef.current) {
      rightLabelRef.current.textContent = target.side === 'right' ? text : '';
      rightLabelRef.current.classList.toggle('bloom-label-visible', target.side === 'right');
    }
  }, [latestEvent]);

  // animate responsive bloom shapes
  useEffect(() => {
    let frame: number;

    const tick = () => {
      const drawn = drawnRef.current;
      const target = targetRef.current;

      const stale = performance.now() - lastEventAtRef.current > IDLE_TIMER;
      const active = target.dataAvailable && !stale;

      const targetLeft = active && target.side === 'left' ? target.intensity : 0;
      const targetRight = active && target.side === 'right' ? target.intensity : 0;

      drawn.left += (targetLeft - drawn.left) * SMOOTHING;
      drawn.right += (targetRight - drawn.right) * SMOOTHING;

      applyBloomSize(leftShapeRef.current, drawn.left);
      applyBloomSize(rightShapeRef.current, drawn.right);

      if (leftLabelRef.current && (!active || target.side !== 'left')) {
        leftLabelRef.current.classList.remove('bloom-label-visible');
      }
      if (rightLabelRef.current && (!active || target.side !== 'right')) {
        rightLabelRef.current.classList.remove('bloom-label-visible');
      }

      frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    return () => {
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    };
  }, []);

  const handleControlsMouseEnter = () => {
    if (!menuOpenRef.current) window.overlayApi.setIgnoreMouseEvents(false);
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    hoverTimerRef.current = window.setTimeout(() => setControlsVisible(true), 3000);
  };
  const handleControlsMouseLeave = () => {
    if (!menuOpenRef.current) window.overlayApi.setIgnoreMouseEvents(true);
    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
    setControlsVisible(false);
  };

  return (
    <div className="bloom-container">
      <div ref={leftShapeRef} className="bloom-shape bloom-shape-left" />
      <div ref={rightShapeRef} className="bloom-shape bloom-shape-right" />

      <div ref={leftLabelRef} className="bloom-label bloom-label-left" />
      <div ref={rightLabelRef} className="bloom-label bloom-label-right" />

      <div
        className={`bloom-controls${controlsVisible ? ' bloom-controls-visible' : ''}`}
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

const root = createRoot(document.getElementById('root')!);
root.render(<BloomOverlay />);
