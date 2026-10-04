import { afterEach, describe, expect, it } from 'vitest';
import { applyPluginAppearance, initializePluginAppearance } from './pluginAppearance';

afterEach(() => {
  document.documentElement.removeAttribute('data-fh-plugin-appearance');
  sessionStorage.removeItem('fh_plugin_appearance');
  window.history.replaceState({}, '', '/');
});

describe('plugin appearance', () => {
  it('does not alter an ordinary site page', () => {
    window.history.replaceState({}, '', '/');
    initializePluginAppearance(false);
    expect(document.documentElement.dataset.fhPluginAppearance).toBeUndefined();
  });

  it('uses only a bounded choice from the plugin bootstrap', () => {
    window.history.replaceState({}, '', '/embed?fh_appearance=orca#fh_bridge=bound-session');
    initializePluginAppearance(true);
    expect(document.documentElement.dataset.fhPluginAppearance).toBe('orca');

    applyPluginAppearance('unexpected');
    expect(document.documentElement.dataset.fhPluginAppearance).toBe('orca');
  });

  it('restores the bound appearance after plugin navigation and reload', () => {
    window.history.replaceState({}, '', '/profile#fh_bridge=bound-session&fh_appearance=orca');
    initializePluginAppearance(true);
    expect(document.documentElement.dataset.fhPluginAppearance).toBe('orca');
  });

  it('honors an explicit FilamentHub choice over a stored Orca choice', () => {
    sessionStorage.setItem('fh_plugin_appearance', 'orca');
    window.history.replaceState({}, '', '/embed?fh_appearance=filamenthub');
    initializePluginAppearance(true);
    expect(document.documentElement.dataset.fhPluginAppearance).toBe('filamenthub');

    window.history.replaceState({}, '', '/profile#fh_bridge=bound-session&fh_appearance=filamenthub');
    sessionStorage.setItem('fh_plugin_appearance', 'orca');
    initializePluginAppearance(true);
    expect(document.documentElement.dataset.fhPluginAppearance).toBe('filamenthub');
  });

  it('ignores an invalid URL choice', () => {
    window.history.replaceState({}, '', '/embed?fh_appearance=unknown');
    initializePluginAppearance(true);
    expect(document.documentElement.dataset.fhPluginAppearance).toBe('filamenthub');
  });
});
