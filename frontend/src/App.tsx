/**
 * This is the menu page window where users can configure their settings and
 * choose which type of audio visualiser they would like, as well as adjust
 * the display and appearance of it.
 *
 * From this window, users can open new windows which will be the audio
 * visualisers themselves.
 */

import { useEffect, useState } from 'react';

function App() {
  // Tracks which overlays are currently open, so each button can show
  // whether clicking it will open or close its overlay. Overlays can also
  // close themselves (e.g. their own Close button), so this is synced from
  // the main process rather than toggled optimistically.
  const [openOverlays, setOpenOverlays] = useState<Record<string, boolean>>({});

  useEffect(() => {
    window.overlayApi.getOverlayStates().then(setOpenOverlays);
    window.overlayApi.onOverlayStateChanged((name, isOpen) => {
      setOpenOverlays((prev) => ({ ...prev, [name]: isOpen }));
    });
  }, []);

  return (
    <div>
      <h1>Menu</h1>

      <h2>Overlays</h2>

      <button
        id="openBloomBtn"
        className={openOverlays.bloom ? 'active' : ''}
        onClick={() => window.overlayApi.toggleOverlay('bloom')}
      >
        Bloom
      </button>
      <button
        id="openRingBtn"
        className={openOverlays.ring ? 'active' : ''}
        onClick={() => window.overlayApi.toggleOverlay('ring')}
      >
        Ring
      </button>
      <button
        id="openCompassBtn"
        className={openOverlays.compass ? 'active' : ''}
        onClick={() => window.overlayApi.toggleOverlay('compass')}
      >
        Compass
      </button>

      <button className="close-menu-btn"
        onClick={() => window.overlayApi.closeMenu()}>
        Close Menu
      </button>
    </div>
  );
}

export default App;