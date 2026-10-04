export type PluginAppearance = 'filamenthub' | 'orca';

const STORAGE_KEY = 'fh_plugin_appearance';

function validAppearance(value: unknown): value is PluginAppearance {
  return value === 'filamenthub' || value === 'orca';
}

function appearanceFrom(value: unknown): PluginAppearance | null {
  return validAppearance(value) ? value : null;
}

export function applyPluginAppearance(value: unknown): void {
  if (!validAppearance(value) || typeof document === 'undefined') return;
  document.documentElement.dataset.fhPluginAppearance = value;
  try {
    sessionStorage.setItem(STORAGE_KEY, value);
  } catch {
    // The bound URL still carries the choice in direct Pages hosts.
  }
}

export function initializePluginAppearance(pluginEmbed: boolean): void {
  if (!pluginEmbed || typeof window === 'undefined') return;
  const query = new URLSearchParams(window.location.search).get('fh_appearance');
  const fragment = new URLSearchParams(window.location.hash.slice(1)).get('fh_appearance');
  let stored: string | null = null;
  try {
    stored = sessionStorage.getItem(STORAGE_KEY);
  } catch {
    // Storage may be partitioned by an iframe host.
  }
  applyPluginAppearance(
    appearanceFrom(query) ?? appearanceFrom(fragment) ?? appearanceFrom(stored) ?? 'filamenthub',
  );
}
