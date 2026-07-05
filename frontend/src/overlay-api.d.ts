declare global {
  interface Window {
    overlayApi: {
      openOverlay: (name: string) => void;
      closeOverlay: (name: string) => void;
      toggleOverlay: (name: string) => void;
      getOverlayStates: () => Promise<Record<string, boolean>>;
      focusMenu: () => void;
      closeMenu: () => void;
      setIgnoreMouseEvents: (ignore: boolean) => void;
      onMenuOpenChanged: (callback: (isOpen: boolean) => void) => void;
      onOverlayStateChanged: (callback: (name: string, isOpen: boolean) => void) => void;
    };
  }
}
export {};