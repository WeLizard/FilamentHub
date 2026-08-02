import { describe, expect, it, vi } from 'vitest';

import {
  importPresetToPlugin,
  installPrinterBundleInPlugin,
  PLUGIN_MESSAGE_SOURCE,
  reportPluginSessionToPlugin,
  requestPluginCapabilities,
  subscribeToPluginNavigation,
} from './pluginBridge';

describe('pluginBridge inbound messages', () => {
  it('accepts navigation only from the trusted parent origin', () => {
    const navigate = vi.fn();
    const unsubscribe = subscribeToPluginNavigation(navigate);
    const data = {
      source: PLUGIN_MESSAGE_SOURCE,
      type: 'navigate',
      path: '/catalog',
    };

    window.dispatchEvent(
      new MessageEvent('message', {
        data,
        origin: 'https://evil.example',
        source: window,
      }),
    );
    expect(navigate).not.toHaveBeenCalled();

    window.dispatchEvent(
      new MessageEvent('message', {
        data,
        origin: window.location.origin,
        source: window,
      }),
    );
    expect(navigate).toHaveBeenCalledWith('/catalog');

    unsubscribe();
  });

  it('sends only the scoped plugin capability across the iframe boundary', () => {
    const originalParent = window.parent;
    const postMessage = vi.fn();
    Object.defineProperty(window, 'parent', {
      configurable: true,
      value: { postMessage },
    });
    window.history.pushState({}, '', '/embed/catalog');

    try {
      reportPluginSessionToPlugin('scoped-plugin-token');
      importPresetToPlugin(42);
      installPrinterBundleInPlugin(7);
      requestPluginCapabilities();

      expect(postMessage).toHaveBeenNthCalledWith(
        1,
        {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'auth-token',
          accessToken: 'scoped-plugin-token',
          refreshToken: '',
        },
        '*',
      );
      expect(postMessage).toHaveBeenNthCalledWith(
        2,
        {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'import-preset',
          presetId: 42,
          token: 'scoped-plugin-token',
        },
        '*',
      );
      expect(postMessage).toHaveBeenNthCalledWith(
        3,
        {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'install-printer-bundle',
          physicalPrinterId: 7,
          token: 'scoped-plugin-token',
        },
        '*',
      );
      expect(postMessage).toHaveBeenNthCalledWith(
        4,
        {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'plugin-capabilities-request',
        },
        '*',
      );
    } finally {
      Object.defineProperty(window, 'parent', {
        configurable: true,
        value: originalParent,
      });
      window.history.pushState({}, '', '/');
    }
  });
});
