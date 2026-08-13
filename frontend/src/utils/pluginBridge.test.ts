import { describe, expect, it, vi } from 'vitest';

import {
  importPresetToPlugin,
  installPrinterBundleInPlugin,
  PLUGIN_MESSAGE_SOURCE,
  reportPluginSessionToPlugin,
  requestHappyHareAction,
  requestPluginCapabilities,
  subscribeToPluginCapabilities,
  subscribeToPluginNavigation,
  subscribeToPluginRecoverList,
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

  it('normalizes current and legacy recovery items without losing account identity', () => {
    const onList = vi.fn();
    const unsubscribe = subscribeToPluginRecoverList(onList);

    window.dispatchEvent(
      new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'recover-list',
          items: [
            {
              key: 'machine:account-a:Voron 2.4',
              kind: 'machine',
              name: 'Voron 2.4',
              account: 'account-a',
              source: 'backup',
              imported: true,
            },
            { name: 'Legacy PLA', imported: false },
          ],
        },
        origin: window.location.origin,
        source: window,
      }),
    );

    expect(onList).toHaveBeenCalledWith([
      {
        key: 'machine:account-a:Voron 2.4',
        kind: 'machine',
        name: 'Voron 2.4',
        account: 'account-a',
        source: 'backup',
        imported: true,
      },
      {
        key: 'Legacy PLA',
        kind: 'filament',
        name: 'Legacy PLA',
        source: 'live',
        imported: false,
      },
    ]);

    unsubscribe();
  });

  it('sends only owned IDs for a Happy Hare action and accepts the matching reply', async () => {
    const originalParent = window.parent;
    const postMessage = vi.fn();
    const parent = { postMessage };
    Object.defineProperty(window, 'parent', { configurable: true, value: parent });
    window.history.pushState({}, '', '/embed/profile');
    const unsubscribe = subscribeToPluginCapabilities(() => undefined);

    try {
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'plugin-capabilities',
          capabilities: ['happy-hare-moonraker'],
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      const pending = requestHappyHareAction('preview', 12, 34);
      const request = postMessage.mock.calls.at(-1)?.[0];

      expect(request).toMatchObject({
        source: PLUGIN_MESSAGE_SOURCE,
        type: 'happy-hare-preview',
        physicalPrinterId: 12,
        materialSystemId: 34,
      });
      expect(request).not.toHaveProperty('host');
      expect(request).not.toHaveProperty('apiKey');
      expect(request).not.toHaveProperty('script');
      expect(request).not.toHaveProperty('token');

      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'happy-hare-result',
          requestId: request.requestId,
          result: {
            ok: true,
            operation: 'preview',
            physicalPrinterId: 12,
            materialSystemId: 34,
            changes: [],
          },
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));

      await expect(pending).resolves.toMatchObject({ ok: true, changes: [] });
    } finally {
      unsubscribe();
      Object.defineProperty(window, 'parent', {
        configurable: true,
        value: originalParent,
      });
      window.history.pushState({}, '', '/');
    }
  });
});
