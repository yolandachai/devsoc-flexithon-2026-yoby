declare global {
  interface Window {
    overlayApi: {
      openOverlay: (name: string) => void;
      closeOverlay: (name: string) => void;
      focusMenu: () => void;
      closeMenu: () => void;
      setIgnoreMouseEvents: (ignore: boolean) => void;
      onMenuOpenChanged: (callback: (isOpen: boolean) => void) => void;
    };
  }
}
export {};