import { useEffect, useState } from 'react';

export interface DirectionEstimate {
  available: boolean,           // true if the direction estimate is valid, false if not enough audio has been heard yet
  mode: "stereo" | "multichannel" | "none"
  pan: number | null,           // -1.0 (left) to 1.0 (right) for stereo, or null if not available
  azimuth_deg: number | null,   // 0.0 (front) to 180.0 (back) for multichannel, or null if not available
  label: string,                // the label of "front", front-left", "back-right", etc.
}

export interface DirectionEstimateEvent {
  label: string,                // the label of the sound that was detected, or "" if none
  confidence: number,           // the confidence of the sound detection, from 0.0 to 1.0
  direction: DirectionEstimate, // the direction estimate of the sound, or null if not available
  timestamp: number,            // the timestamp of the event, in milliseconds since the epoch (mostly for debugging)
}

const SERVER_URL = 'ws://localhost:8765';
const RECONNECT_DELAY_MS = 1000;

type Listener = (event: DirectionEstimateEvent) => void;

const listeners = new Set<Listener>();
let socket: WebSocket | null = null;

function connect() {
  socket = new WebSocket(SERVER_URL);

  socket.onmessage = (message) => {
    const event: DirectionEstimateEvent = JSON.parse(message.data);
    listeners.forEach((listener) => listener(event));
  };

  socket.onclose = () => {
    socket = null;
    setTimeout(connect, RECONNECT_DELAY_MS);
  };

  socket.onerror = () => {
    socket?.close();
  };
}

// Subscribe to every event broadcast by the backend server.py pipeline.
// meaning that the listener will be called with every new DirectionEstimateEvent 
// as it arrives.
export function subscribeToEvents(listener: Listener): () => void {
  if (!socket) {
    connect();
  }
  listeners.add(listener);
  return () => listeners.delete(listener);
}

// React hook: gives an overlay the most recent event, updating as new ones arrive.
// Usage in any overlay component:
//   const event = useLatestEvent();
//   if (!event) return null; // nothing heard yet
export function useLatestEvent(): DirectionEstimateEvent | null {
  const [event, setEvent] = useState<DirectionEstimateEvent | null>(null);

  useEffect(() => subscribeToEvents(setEvent), []);

  return event;
}

// Example usage in a React component:
// function MyOverlay() {
//   const event = useLatestEvent(); // which returns the json seen above
//   if (!event) return null; // nothing heard yet
//   return <div>Detected sound: {event.label} at {event.direction?.label}</div>;
// }