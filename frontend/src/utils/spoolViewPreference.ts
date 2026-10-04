export function spoolViewPreferenceKey(pluginEmbedded: boolean): string {
  return pluginEmbedded ? 'plugin.spoolsView' : 'profile.spoolsView';
}
