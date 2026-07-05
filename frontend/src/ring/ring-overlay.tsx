import { createRoot } from 'react-dom/client';
import './ring-overlay.css'
import { useEffect, useState } from 'react';

function RingOverlay() {
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    window.overlayApi.onMenuOpenChanged(setMenuOpen);
  }, []);

  return (
    <div>
      {/* open menu */}
      <button
        disabled={menuOpen}
        style={menuOpen ? { pointerEvents: 'none' } : undefined}
        onMouseEnter={() => window.overlayApi.setIgnoreMouseEvents(false)}
        onMouseLeave={() => window.overlayApi.setIgnoreMouseEvents(true)}
        onClick={() => window.overlayApi.focusMenu()}
      >
        Menu
      </button>

      {/* close this overlay */}
      <button
        disabled={menuOpen}
        style={menuOpen ? { pointerEvents: 'none' } : undefined}
        onMouseEnter={() => window.overlayApi.setIgnoreMouseEvents(false)}
        onMouseLeave={() => window.overlayApi.setIgnoreMouseEvents(true)}
        onClick={() => window.overlayApi.closeOverlay('ring')}
      >
        Close
      </button>
    </div>
  );
}

const root = createRoot(document.getElementById('root')!);
root.render(<RingOverlay />);