import { app, BrowserWindow, ipcMain, screen } from 'electron';
import path from 'node:path';
import started from 'electron-squirrel-startup';

// Handle creating/removing shortcuts on Windows when installing/uninstalling.
if (started) {
  app.quit();
}

/**
 * Menu window functionaltiy.
 * 
 * opened when the app starts, and allows users to launch the audio visualiser
 * interfaces.
 */

let menuWindow: BrowserWindow | null = null;

// global state flags

// when isMenuOpen is true, the menu is open and it becomes the window on the
// very top. any overlay windows which are open are no longer interactable, and
// users cannot click on them.
let isMenuOpen = false;

// differentiates between if the menu window is actually closing or if it should
// just be hidden. when isQuitting is true, then the window should actually
// close. this allows the app to be closed instead of being in a limbo state.
let isQuitting = false;

/**
 * creates the menu window. will be created when the app starts, as well as when
 * called to in the overlay windows.
 * @returns 
 */
const createMenuWindow = () => {
  const mainWindow = new BrowserWindow({
    title: 'Menu Page',
    width: 800,
    height: 600,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  mainWindow.setMenu(null);

  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(
      path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`),
    );
  }

  menuWindow = mainWindow;

  // for when the menu window is actually closed and not on hide
  mainWindow.on('closed', () => {
    menuWindow = null;
  });

  // puts the menu window on hide
  mainWindow.on('close', (e) => {
    if (isQuitting) return;
    e.preventDefault();
    closeMenuWindow();
  });

  // mainWindow.webContents.openDevTools();

  return mainWindow;
};

/**
 * when the menu is open, overlays should no longer be on top and should not
 * be accessible.
 * @returns 
 */
function focusMenuWindow() {
  isMenuOpen = true;

  overlayWindows.forEach((win) => {
    if (win.isDestroyed()) return;
    win.setIgnoreMouseEvents(true, { forward: false });
    win.setAlwaysOnTop(false);
    win.setFocusable(false);
    win.webContents.send('menu-open-changed', true);
  });

  // create menu window if it doesn't exist.
  if (!menuWindow || menuWindow.isDestroyed()) {
    createMenuWindow();
    // wait for window to be ready.
    menuWindow!.once('ready-to-show', () => {
      menuWindow!.setAlwaysOnTop(true);
      menuWindow!.show();
      menuWindow!.moveTop();
      menuWindow!.focus();
    });
    return;
  }

  // if menu window already exists, show.
  menuWindow.setAlwaysOnTop(true);
  menuWindow.show();
  menuWindow.moveTop();
  menuWindow.focus();
}

/**
 * quits app whena ll windows are closed.
 */
function quitIfNoVisibleWindows() {
  const anyVisible = BrowserWindow.getAllWindows().some(
    (w) => !w.isDestroyed() && w.isVisible()
  );
  if (!anyVisible) {
    app.quit();
  }
}

/**
 * when the menu window is closed, overlay windows should be at the top again.
 */
function closeMenuWindow() {
  isMenuOpen = false;

  if (menuWindow && !menuWindow.isDestroyed()) {
    menuWindow.setAlwaysOnTop(false);
    menuWindow.hide();
  }

  // put overlay windows back on top again
  overlayWindows.forEach((win) => {
    if (win.isDestroyed()) return;
    win.setAlwaysOnTop(true);
    win.setIgnoreMouseEvents(true, { forward: true });
    win.setFocusable(true);
    win.webContents.send('menu-open-changed', false);
    win.moveTop();
  });

  quitIfNoVisibleWindows();
}

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
// Some APIs can only be used after this event occurs.
app.on('ready', createMenuWindow);

/**
 * closes the app for good, not hiding it.
 */
app.on('before-quit', () => {
  isQuitting = true;
});

/**
 * Overlay window functionality.
 * 
 * opened from the menu window. used to display the audio visualisers.
 */

// Overlay windows keyed by name, so re-clicking a menu button focuses the
// existing window instead of opening a duplicate.
const overlayWindows = new Map<string, BrowserWindow>();

// Maps overlay name -> the folder/file its renderer HTML lives in.
const OVERLAYS: Record<string, {
  folder: string;
  file: string;
  options?: Electron.BrowserWindowConstructorOptions
}> = {
  bloom: {
    folder: 'bloom',
    file: 'bloom-overlay.html',
    options: {
      fullscreen: true
    }
  },

  ring: { 
    folder: 'ring', 
    file: 'ring-overlay.html' ,
    options: {
      fullscreen: true
    }
  },

  compass: { 
    folder: 'compass', 
    file: 'compass-overlay.html',
    options: {
      fullscreen: true
    }
  },
};

/**
 * opens overlay window and hides the menu window.
 * @param name
 * @returns 
 */
function openOverlayWindow(name: string) {
  const existing = overlayWindows.get(name);
  if (existing) {
    existing.focus();
    return;
  }

  const overlay = OVERLAYS[name];
  if (!overlay) return;

  // hide menu to save its state.
  isMenuOpen = false;
  menuWindow?.hide();
  menuWindow?.setAlwaysOnTop(false);

  // pin ring overlay to the bottom left of hte screen
  const RING_WINDOW_SIZE = 360;
  const RING_WINDOW_MARGIN = 24;

  let windowBounds: Electron.Rectangle | undefined;
  if (name === 'ring') {
    const { workArea } = screen.getPrimaryDisplay();
    windowBounds = {
      width: RING_WINDOW_SIZE,
      height: RING_WINDOW_SIZE,
      x: workArea.x + RING_WINDOW_MARGIN,
      y: workArea.y + workArea.height - RING_WINDOW_SIZE - RING_WINDOW_MARGIN,
    };
  }

  const win = new BrowserWindow({
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    ...overlay.options,
    ...windowBounds,
    hasShadow: false,
    thickFrame: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  win.setMenu(null);

  // 'screen-saver' is the highest always-on-top level electron exposes,
  // needed so the overlay stays above other apps running in exclusive
  // fullscreen (e.g. games), which plain alwaysOnTop does not cover.
  win.setAlwaysOnTop(true, 'screen-saver');
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  // click through the window
  win.setIgnoreMouseEvents(true, { forward: true });

  const rendererBase = MAIN_WINDOW_VITE_DEV_SERVER_URL
    ? `${MAIN_WINDOW_VITE_DEV_SERVER_URL}/src/${overlay.folder}/${overlay.file}`
    : undefined;

  if (rendererBase) {
    win.loadURL(rendererBase);
  } else {
    win.loadFile(
      path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/src/${overlay.folder}/${overlay.file}`),
    );
  }

  // win.webContents.openDevTools();

  win.on('closed', () => {
    overlayWindows.delete(name);
    notifyOverlayState(name, false);
  });
  overlayWindows.set(name, win);
  notifyOverlayState(name, true);
}

/**
 * closes overlay windows
 * @param name
 */
function closeOverlayWindow(name: string) {
  const win = overlayWindows.get(name);
  if (win) {
    win.close();
  }
  quitIfNoVisibleWindows();
}

/**
 * toggle overlay windows from menu window
 * @param name
 */
function toggleOverlayWindow(name: string) {
  if (overlayWindows.has(name)) {
    closeOverlayWindow(name);
  } else {
    openOverlayWindow(name);
  }
}

/**
 * tells the menu window whether a given overlay is currently open
 * @param name
 * @param isOpen
 */
function notifyOverlayState(name: string, isOpen: boolean) {
  if (menuWindow && !menuWindow.isDestroyed()) {
    menuWindow.webContents.send('overlay-state-changed', name, isOpen);
  }
}

/**
 * IPC handlers
 */

ipcMain.on('open-overlay', (_event, name: string) => {
  openOverlayWindow(name);
});

ipcMain.on('close-overlay', (_event, name: string) => {
  closeOverlayWindow(name);
});

ipcMain.on('toggle-overlay', (_event, name: string) => {
  toggleOverlayWindow(name);
});

ipcMain.handle('get-overlay-states', () => {
  const states: Record<string, boolean> = {};
  for (const name of Object.keys(OVERLAYS)) {
    states[name] = overlayWindows.has(name);
  }
  return states;
});

ipcMain.on('set-ignore-mouse-events', (event, ignore: boolean) => {
  // users cannot interact with the overlays whilst the menu is open.
  if (isMenuOpen) return;

  const targetWindow = BrowserWindow.fromWebContents(event.sender);
  if (!targetWindow) return;

  if (ignore) {
    targetWindow.setIgnoreMouseEvents(true, { forward: true });
  } else {
    targetWindow.setIgnoreMouseEvents(false);
  }
});

ipcMain.on('focus-menu', () => {
  focusMenuWindow();
});

ipcMain.on('close-menu', () => {
  closeMenuWindow();
});

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  app.quit();
});

app.on('activate', () => {
  // On OS X it's common to re-create a window in the app when the
  // dock icon is clicked and there are no other windows open.
  if (BrowserWindow.getAllWindows().length === 0) {
    createMenuWindow();
  }
});

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and import them here.