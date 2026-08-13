import { useEffect, useState } from 'react';

import {
  isPluginEmbed,
  requestPluginCapabilities,
  subscribeToPluginCapabilities,
} from '../utils/pluginBridge';

export type OrcaBridgeCapability = 'exportFilamentPresets' | 'exportPrinterProfiles' | 'exportPrintProfiles';

const hasLegacyCapability = (capability: OrcaBridgeCapability): boolean => (
  typeof window !== 'undefined'
  && typeof window.filamenthub?.[capability] === 'function'
);

export function useOrcaBridgeCapability(capability: OrcaBridgeCapability): boolean {
  const [available, setAvailable] = useState(() => hasLegacyCapability(capability));

  useEffect(() => {
    let attempts = 0;
    let intervalId: number | null = null;
    let pluginProfileSyncAvailable = false;
    const check = () => {
      const nextAvailable = hasLegacyCapability(capability) || pluginProfileSyncAvailable;
      setAvailable(nextAvailable);
      attempts += 1;
      if ((nextAvailable || attempts >= 30) && intervalId !== null) {
        window.clearInterval(intervalId);
        intervalId = null;
      }
    };

    check();
    if (!hasLegacyCapability(capability)) {
      intervalId = window.setInterval(check, 1000);
    }
    window.addEventListener('focus', check);
    const unsubscribe = isPluginEmbed()
      ? subscribeToPluginCapabilities((capabilities) => {
          pluginProfileSyncAvailable = capabilities.has('profile-sync');
          check();
        })
      : undefined;
    if (unsubscribe) requestPluginCapabilities();

    return () => {
      if (intervalId !== null) window.clearInterval(intervalId);
      window.removeEventListener('focus', check);
      unsubscribe?.();
    };
  }, [capability]);

  return available;
}
