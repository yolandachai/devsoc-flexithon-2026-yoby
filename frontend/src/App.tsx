/**
 * This is the menu page window where users can configure their settings and
 * choose which type of audio visualiser they would like, as well as adjust
 * the display and appearance of it.
 *
 * From this window, users can open new windows which will be the audio
 * visualisers themselves.
 */

import { useEffect } from 'react';

declare global {
  interface Window {
    overlayApi: {
      openOverlay: (name: string) => void;
    };
  }
}

/**
 * Button to create a window for the first audio visualiser type.
 * The bloom overlay (for 2D games) design. This design has a bloom effect on
 * the left and right sides of the screen corresponding to the direction and
 * intensity of sound.
 */
function wireBloomBtn() {
  const openBloomBtn = document.getElementById('openBloomBtn');
  if (openBloomBtn) {
    openBloomBtn.addEventListener('click', function (event) {
      window.overlayApi.openOverlay('bloom');
    });
  }
}

/**
 * Button to create a window for the second audio visualiser type.
 * The ring overlay (360 degree) design. This design has a hollow ring wherein
 * its sides increase in width corresponding to the direction and intensity of
 * sound.
 */
function wireRingBtn() {
  const openRingBtn = document.getElementById('openRingBtn');
  if (openRingBtn) {
    openRingBtn.addEventListener('click', function (event) {
      window.overlayApi.openOverlay('ring');
    });
  }
}

/**
 * Button to create a window for the third audio visualiser type.
 * The compass overlay design. This design shows a horizontal
 * strip with a pin per detected sound at its estimated direction, labelled
 * with what the sound is.
 */
function wireCompassBtn() {
  const openCompassBtn = document.getElementById('openCompassBtn');
  if (openCompassBtn) {
    openCompassBtn.addEventListener('click', function (event) {
      window.overlayApi.openOverlay('compass');
    });
  }
}

function App() {
  // Wired up after mount (rather than at module load) so the buttons above
  // exist in the DOM when getElementById runs.
  useEffect(() => {
    wireBloomBtn();
    wireRingBtn();
    wireCompassBtn();
  }, []);

  return (
    <div>
      <h1>Menu</h1>

      <h2>Overlays</h2>

      <button id="openBloomBtn">Bloom</button>
      <button id="openRingBtn">Ring</button>
      <button id="openCompassBtn">Compass</button>
    </div>
  );
}

export default App;