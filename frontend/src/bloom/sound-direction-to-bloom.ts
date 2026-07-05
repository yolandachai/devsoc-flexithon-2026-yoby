/**
 * Converts direction estimated audio into data that can be mapped to the
 * bloom interface (for the bloom overlay).
 *
 *  {
 *    side: ('left' | 'right' | null)   which side the sound is coming from
 *    intensity: (number)               0 (nothing) to 1 (strongest) on that side
 *    dataAvailable: (boolean)          whether there's a usable side reading
 *  }
 */

import type { DirectionEstimate } from '../server/api';

// Labels reported by the backend (see backend/direction.py) that count as
// "on a side" for the purposes of this overlay. Anything else (center,
// front, back, silent, unknown) is treated as no bloom.
const LEFT_LABELS = new Set(['left', 'slightly left', 'front-left', 'back-left']);
const RIGHT_LABELS = new Set(['right', 'slightly right', 'front-right', 'back-right']);

export interface DataForBloom {
  side: 'left' | 'right' | null;
  intensity: number;
  dataAvailable: boolean;
}

const NO_DATA: DataForBloom = { side: null, intensity: 0, dataAvailable: false };

export function dataForBloom(
  direction: DirectionEstimate,
  confidence: number): DataForBloom {

  if (!direction.available) return NO_DATA;

  // stereo: pan of -1 (left) to 1 (right), sign gives the side directly.
  if (direction.mode === 'stereo' && direction.pan !== null) {
    if (LEFT_LABELS.has(direction.label)) {
      return { side: 'left', intensity: confidence, dataAvailable: true };
    }
    if (RIGHT_LABELS.has(direction.label)) {
      return { side: 'right', intensity: confidence, dataAvailable: true };
    }
    return NO_DATA;
  }

  // multichannel: azimuth of -180 (left) .. 180 (right), via label bucket
  // since front-left/back-left are both "left enough" for this overlay.
  if (direction.mode === 'multichannel' && direction.azimuth_deg !== null) {
    if (LEFT_LABELS.has(direction.label)) {
      return { side: 'left', intensity: confidence, dataAvailable: true };
    }
    if (RIGHT_LABELS.has(direction.label)) {
      return { side: 'right', intensity: confidence, dataAvailable: true };
    }
    return NO_DATA;
  }

  return NO_DATA;
}
