import { app, BrowserWindow, ipcMain } from 'electron';
import path from 'node:path';
import started from 'electron-squirrel-startup';

// Handle creating/removing shortcuts on Windows when installing/uninstalling.
if (started) {
  app.quit();
}

/**
 * Menu window.
 */

const createMenuWindow = () => {
  // Create the browser window for the menu.
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

  // and load the index.html of the app.
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(
      path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`),
    );
  }

  mainWindow.setIgnoreMouseEvents(true);

  // Open the DevTools.
  mainWindow.webContents.openDevTools();
};

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
// Some APIs can only be used after this event occurs.
app.on('ready', createMenuWindow);

/**
 * Overlay windows.
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

function openOverlayWindow(name: string) {
  const existing = overlayWindows.get(name);
  if (existing) {
    existing.focus();
    return;
  }

  const overlay = OVERLAYS[name];
  if (!overlay) return;

  const win = new BrowserWindow({
    frame: false,
    transparent: false,
    resizable: false,
    alwaysOnTop: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  win.setMenu(null);

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

  win.webContents.openDevTools();
  win.on('closed', () => overlayWindows.delete(name));
  overlayWindows.set(name, win);
}

ipcMain.on('open-overlay', (_event, name: string) => {
  openOverlayWindow(name);
});


// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
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