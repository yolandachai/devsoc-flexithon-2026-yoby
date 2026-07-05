/**
 * This is the menu page window where users can configure their settings and
 * choose which type of audio visualiser they would like, as well as adjust
 * the display and appearance of it.
 * 
 * From this window, users can open new windows which will be the audio
 * visualisers themselves.
 */

import type { BrowserWindow as BrowserWindowType } from 'electron';
import { BrowserWindow } from '@electron/remote';
import * as path from 'path';
import * as url from 'url';

/**
 * Button to create a window for the first audio visualiser type.
 * The bloom overlay (for 2D games) design. This design has a bloom effect on
 * the left and right sides of the screen corresponding to the direction and
 * intensity of sound.
 */
let bloomWin: BrowserWindowType | null = null;
const openBloomBtn = document.getElementById('openBloomBtn');
if (openBloomBtn) {
  openBloomBtn.addEventListener('click', function (event) {
    if (bloomWin) {
      bloomWin.focus();
      return;
    }
    bloomWin = new BrowserWindow();

    bloomWin.loadURL(url.format({
      pathname: path.join(__dirname, 'bloom', 'bloom-overlay.html'),
      protocol: 'file',
      slashes: true
    }));
    bloomWin.webContents.openDevTools();
  });
}

/**
 * Button to create a window for the second audio visualiser type.
 * The ring overlay (360 degree) design. This design has a hollow ring wherein
 * its sides increase in width corresponding to the direction and intensity of
 * sound.
 */
let ringWin: BrowserWindowType | null = null;
const openRingBtn = document.getElementById('openRingBtn');
if (openRingBtn) {
  openRingBtn.addEventListener('click', function (event) {
    if (ringWin) {
      ringWin.focus();
      return;
    }
    ringWin = new BrowserWindow();

    ringWin.loadURL(url.format({
      pathname: path.join(__dirname, 'ring', 'ring-overlay.html'),
      protocol: 'file',
      slashes: true
    }));
    ringWin.webContents.openDevTools();
  });
}

function App() {
  return (
    <div>
      <h1>Header</h1>
    </div>
  );
}

export default App;
