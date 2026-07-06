import { createRoot } from 'react-dom/client';
import './ring-overlay.css'
import { useEffect, useState, useRef } from 'react';
import { useLatestEvent } from '../server/api';
import { dataForRing } from './sound-direction-to-ring';

const SMOOTHING = 0.25;
const IDLE_TIMER = 1500; // in ms
const CENTER = 200;
const BASE_RADIUS = 120;
const MIN_THICKNESS = 10;
const MAX_THICKNESS = 100;
const SEGMENTS = 180;

function RingOverlay() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuOpenRef = useRef(false);

  const [controlsVisible, setControlsVisible] = useState(false);
  const hoverTimerRef = useRef<number | null>(null);

  const latestEvent = useLatestEvent();

  const drawnRef = useRef({ degree: 0, intensity: 0 });
  const lastEventAtRef = useRef<number>(0);

  const pathRef = useRef<SVGPathElement>(null);
  const labelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    window.overlayApi.onMenuOpenChanged((isOpen) => {
      menuOpenRef.current = isOpen;
      setMenuOpen(isOpen);
    });
  }, []);

  const targetRef = useRef({ degree: 0, intensity: 0, dataAvailable: false });
  useEffect(() => {
    if (!latestEvent) return;
    const target = dataForRing(latestEvent.direction, latestEvent.confidence);
    targetRef.current = target;
    lastEventAtRef.current = performance.now();
 
    if (labelRef.current) {
      labelRef.current.textContent = target.dataAvailable
        ? `${latestEvent.label || 'Sound'} — ${latestEvent.direction.label}`
        : '';
      labelRef.current.classList.toggle('ring-label-visible', target.dataAvailable);
    }
  }, [latestEvent]);

  // animate repsonsive ring
  useEffect(() => {
    let frame: number;
 
    const tick = () => {
      const drawn = drawnRef.current;
      const target = targetRef.current;
 
      // if no response from backend/no data, go back to the default state of
      // the ring.
      const stale = performance.now() - lastEventAtRef.current > IDLE_TIMER;
      const targetIntensity = stale || !target.dataAvailable ? 0 : target.intensity;
 
      drawn.intensity += (targetIntensity - drawn.intensity) * SMOOTHING;
 
      if (target.dataAvailable && !stale) {
        let delta = target.degree - drawn.degree;
        if (delta > 180) delta -= 360;
        if (delta < -180) delta += 360;
        drawn.degree = (drawn.degree + delta * SMOOTHING + 360) % 360;
      }
 
      const d = ringElement(drawn.intensity, drawn.degree);
      if (pathRef.current) pathRef.current.setAttribute('d', d);

      if (labelRef.current && (stale || !target.dataAvailable)) {
        labelRef.current.classList.remove('ring-label-visible');
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
    <div className="main-container">
      <svg className="ring-svg" viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg">
        <path ref={pathRef} className="ring-main" />
      </svg>

      <div ref={labelRef} className="ring-label" />

      <div
        className={`ring-controls${controlsVisible ? ' ring-controls-visible' : ''}`}
        onMouseEnter={handleControlsMouseEnter}
        onMouseLeave={handleControlsMouseLeave}
      >
        <button
          className="ring-btn"
          disabled={menuOpen}
          onClick={() => {
            if (menuOpenRef.current) return;
            window.overlayApi.focusMenu();
            window.overlayApi.closeOverlay('ring');
          }}
        >
          Menu
        </button>
        <button
          className="ring-btn ring-btn-close"
          disabled={menuOpen}
          onClick={() => { if (!menuOpenRef.current) window.overlayApi.closeOverlay('ring'); }}
        >
          Close
        </button>
      </div>
    </div>
  );
}

/**
 * Creating the ring element itself.
 */
function ringElement(intensity: number, degree: number): string {
  const outerPoints: string[] = [];
  const innerPoints: string[] = [];
 
  // calculate/convert the sound direction for each degree
  for (let i = 0; i <= SEGMENTS; i++) {
    const segDeg = (360 / SEGMENTS) * i;
    const segRad = ((segDeg - 90) * Math.PI) / 180;
 
    let diff = Math.abs(segDeg - degree);
    if (diff > 180) diff = 360 - diff;
 
    // makes it smooth.
    const falloff = Math.max(0, Math.cos((diff / 180) * Math.PI));
    const boost = falloff * intensity;
 
    // how far out the circle can grow.
    const thickness = MIN_THICKNESS + (MAX_THICKNESS - MIN_THICKNESS) * boost;
    const outerRadius = BASE_RADIUS + thickness;
 
    const ox = CENTER + outerRadius * Math.cos(segRad);
    const oy = CENTER + outerRadius * Math.sin(segRad);
    const ix = CENTER + BASE_RADIUS * Math.cos(segRad);
    const iy = CENTER + BASE_RADIUS * Math.sin(segRad);
 
    outerPoints.push(`${ox.toFixed(2)},${oy.toFixed(2)}`);
    innerPoints.push(`${ix.toFixed(2)},${iy.toFixed(2)}`);
  }
 
  const outerPath = `M${outerPoints.join('L')}Z`;
  const innerPath = `M${innerPoints.reverse().join('L')}Z`;
 
  return `${outerPath} ${innerPath}`;
}

const root = createRoot(document.getElementById('root')!);
root.render(<RingOverlay />);