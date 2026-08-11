import { useEffect, useState } from 'react';

type OrcaBridgeCapability = 'exportFilamentPresets' | 'exportPrinterProfiles' | 'exportPrintProfiles';

const hasCapability = (capability: OrcaBridgeCapability): boolean => (
  typeof window !== 'undefined'
  && Boolean(window.filamenthub?.[capability] || window.wx?.postMessage)
);

export function useOrcaBridgeCapability(capability: OrcaBridgeCapability): boolean {
  const [available, setAvailable] = useState(() => hasCapability(capability));

  useEffect(() => {
    let attempts = 0;
    let intervalId: number | null = null;
    const check = () => {
      const nextAvailable = hasCapability(capability);
      setAvailable(nextAvailable);
      attempts += 1;
      if ((nextAvailable || attempts >= 30) && intervalId !== null) {
        window.clearInterval(intervalId);
        intervalId = null;
      }
    };

    check();
    if (!hasCapability(capability)) {
      intervalId = window.setInterval(check, 1000);
    }
    window.addEventListener('focus', check);

    return () => {
      if (intervalId !== null) window.clearInterval(intervalId);
      window.removeEventListener('focus', check);
    };
  }, [capability]);

  return available;
}
