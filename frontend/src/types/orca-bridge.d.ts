/** OrcaSlicer WebView C++ bridge, WeChat MiniApp bridge, and experimental Web APIs — global window augmentation */

declare global {
  interface Window {
    /** BarcodeDetector Web API — not yet in TypeScript's lib.dom.d.ts */
    BarcodeDetector?: new(options?: { formats?: string[] }) => {
      detect: (source: unknown) => Promise<Array<{ rawValue?: string }>>;
    };
    filamenthub?: {
      developerMode?: boolean;
      importProfile?: (...args: unknown[]) => unknown;
      navigate?: (path: string) => void;
      exportFilamentPresets?: () => Promise<{ message?: string }>;
      exportPrinterProfiles?: () => Promise<{ message?: string }>;
      exportPrintProfiles?: () => Promise<{ message?: string }>;
      sendLoginSuccess?: (accessToken: string, userId: number, refreshToken: string) => void;
      showNotification?: (message: string, type?: string) => void;
      scanOrphanedPresets?: () => Promise<void>;
    };
    wx?: {
      postMessage?: (message: string) => void;
    };
  }
}

export {};
