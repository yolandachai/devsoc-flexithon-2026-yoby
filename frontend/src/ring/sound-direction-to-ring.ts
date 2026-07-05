/**
 * Converts the direction estimated audio to data that can be mapped to a ring
 * interface (for the ring overlay).
 * 
 * The data returned to be used for the ring interface consists of a degree and
 * an intensity. The degree shows the angle at which hte sound is coming from,
 * wherein 0-degrees is the direction the player character is facing. The
 * intensity is a number from 0 to 1, with 1 being the strongest possible noise
 * and 0 being no noise at all.
 * 
 * Since sound is not always available, there is also a 'dataAvailable' field
 * which shows whether data is available at this moment.
 * 
 * tldr;
 *  {
 *    degree: (number)          the degree that the sound is coming from
 *    intensity: (number)       the intensity of the sound
 *    dataAvailable: (boolean)  whether data is available at this time
 *  }
 */

import type { DirectionEstimate } from '../server/api';

const SOUND_FROM_FRONT = 0;
const MIN_INTENSITY = 0;

export interface DataForRing {
  degree: number;
  intensity: number;
  dataAvailable: boolean;
}

export function toRingTarget(
  direction: DirectionEstimate,
  confidence: number): DataForRing {
  
  // sound unavailable for this particular time.
  if (!direction.available) {
    return {
      degree: SOUND_FROM_FRONT, 
      intensity: MIN_INTENSITY, 
      dataAvailable: false 
    };
  }
 
  // stereo differentiates between left and right as: left = -1,
  // right = 1, front = 0.
  if (direction.mode === 'stereo' && direction.pan !== null) {
    const deg = (direction.pan * 90 + 360) % 360;
    return {
      degree: deg,
      intensity: confidence,
      dataAvailable: true
    };
  }
 
  // multichannel differentiates between left and right as: left = -180 degrees,
  // right = 180 degrees, front = 0 degrees.
  if (direction.mode === 'multichannel' && direction.azimuth_deg !== null) {
    const deg = (direction.azimuth_deg + 360) % 360;
    return { 
      degree: deg,
      intensity: confidence,
      dataAvailable: true
    };
  }
 
  // no sound.
  return {
    degree: SOUND_FROM_FRONT, 
    intensity: MIN_INTENSITY, 
    dataAvailable: false 
  };
}
