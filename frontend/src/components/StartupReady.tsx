import { useLayoutEffect, type ReactNode } from 'react';

/** Only a committed React screen may dismiss the independent startup panel. */
export function StartupReady({ children }: { children: ReactNode }) {
  useLayoutEffect(() => {
    window.dispatchEvent(new Event('fh:startup-ready'));
    // The application can still load when the separate watchdog request failed.
    // In that case no event listener exists to remove the static fallback.
    document.getElementById('fh-startup')?.remove();
  }, []);
  return children;
}

export function reportStartupFailure(): void {
  // Never send the exception, URL or fragment into the recovery UI.
  window.dispatchEvent(new Event('fh:startup-failed'));
}
