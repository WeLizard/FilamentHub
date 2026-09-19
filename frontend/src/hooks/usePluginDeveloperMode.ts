import { useEffect, useState } from 'react';

import {
  isPluginDeveloperMode,
  isPluginEmbed,
  requestPluginCapabilities,
  subscribeToPluginCapabilities,
} from '../utils/pluginBridge';

export function usePluginDeveloperMode(): boolean {
  const [developerMode, setDeveloperMode] = useState(isPluginDeveloperMode);

  useEffect(() => {
    if (!isPluginEmbed()) return;
    const unsubscribe = subscribeToPluginCapabilities(() => setDeveloperMode(isPluginDeveloperMode()));
    requestPluginCapabilities();
    return unsubscribe;
  }, []);

  return developerMode;
}
