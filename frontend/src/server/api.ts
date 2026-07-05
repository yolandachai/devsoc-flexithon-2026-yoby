const socket = new WebSocket('ws://localhost:8765');

export interface DirectionEstimate {
  available: boolean,
  mode: "stereo" | "multichannel" | "none"
  pan: number | null,
  azimuth_deg: number | null,
  label: string,
}

export interface DirectionEstimateEvent {
  label: string,
  confidence: number,
  direction: DirectionEstimate,
  timestamp: number,
}
