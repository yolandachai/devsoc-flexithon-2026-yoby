// See the Electron documentation for details on how to use preload scripts:
// https://www.electronjs.org/docs/latest/tutorial/process-model#preload-scripts

import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('overlayApi', {
  openOverlay: (name: string) => ipcRenderer.send('open-overlay', name),
  closeOverlay: (name: string) => ipcRenderer.send('close-overlay', name),
  toggleOverlay: (name: string) => ipcRenderer.send('toggle-overlay', name),
  getOverlayStates: () => ipcRenderer.invoke('get-overlay-states'),
  setIgnoreMouseEvents: (ignore: boolean) => ipcRenderer.send('set-ignore-mouse-events', ignore),
  focusMenu: () => ipcRenderer.send('focus-menu'),
  closeMenu: () => ipcRenderer.send('close-menu'),
  onMenuOpenChanged: (callback: (isOpen: boolean) => void) => {
    ipcRenderer.on('menu-open-changed', (_event, isOpen: boolean) => callback(isOpen));
  },
  onOverlayStateChanged: (callback: (name: string, isOpen: boolean) => void) => {
    ipcRenderer.on('overlay-state-changed', (_event, name: string, isOpen: boolean) => callback(name, isOpen));
  },
});