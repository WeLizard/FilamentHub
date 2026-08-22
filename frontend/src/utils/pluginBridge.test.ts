import { describe, expect, it, vi } from 'vitest';

import {
  importPresetToPlugin,
  installPrinterBundleInPlugin,
  PLUGIN_MESSAGE_SOURCE,
  reportPluginSessionToPlugin,
  requestBambuMaterialAction,
  requestHappyHareAction,
  requestPluginProfileSync,
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

  it('sends only the scoped plugin capability across the iframe boundary', async () => {
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
      const bundlePending = installPrinterBundleInPlugin(7);
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
          requestId: expect.any(String),
          physicalPrinterId: 7,
          token: 'scoped-plugin-token',
        },
        '*',
      );
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'sync-result',
          text: 'installed',
        },
        origin: window.location.origin,
        source: window.parent,
      }));
      await expect(bundlePending).resolves.toEqual({ message: 'installed' });
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

  it('waits for the matching sync and printer-bundle result', async () => {
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
          capabilities: ['profile-sync-scopes-v1', 'printer-bundle-result-v1'],
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));

      const syncing = requestPluginProfileSync('machine');
      const syncRequest = postMessage.mock.calls.at(-1)?.[0];
      expect(syncRequest).toMatchObject({ type: 'sync', scope: 'machine' });
      let syncSettled = false;
      void syncing.finally(() => { syncSettled = true; });
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'sync-result',
          operationId: 'another-operation',
          status: 'success',
          text: 'unrelated',
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      await Promise.resolve();
      expect(syncSettled).toBe(false);
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'sync-result',
          operationId: syncRequest.operationId,
          status: 'success',
          text: 'machine synced',
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      await expect(syncing).resolves.toEqual({ message: 'machine synced' });

      const installing = installPrinterBundleInPlugin(7);
      const bundleRequest = postMessage.mock.calls.at(-1)?.[0];
      let bundleSettled = false;
      void installing.finally(() => { bundleSettled = true; });
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'printer-bundle-result',
          requestId: 'another-request',
          status: 'success',
          text: 'unrelated',
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      await Promise.resolve();
      expect(bundleSettled).toBe(false);
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'printer-bundle-result',
          requestId: bundleRequest.requestId,
          status: 'success',
          text: 'bundle installed',
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      await expect(installing).resolves.toEqual({ message: 'bundle installed' });
    } finally {
      unsubscribe();
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

      const expectedDesiredAssignments = [
        { gate: 0, spool_id: null },
        { gate: 1, spool_id: 42 },
      ];
      const adopting = requestHappyHareAction(
        'adopt',
        12,
        34,
        expectedDesiredAssignments,
      );
      const adoptRequest = postMessage.mock.calls.at(-1)?.[0];
      expect(adoptRequest).toMatchObject({
        source: PLUGIN_MESSAGE_SOURCE,
        type: 'happy-hare-adopt',
        physicalPrinterId: 12,
        materialSystemId: 34,
        expectedDesiredAssignments,
      });
      expect(adoptRequest).not.toHaveProperty('actualSpoolIds');
      expect(adoptRequest).not.toHaveProperty('host');
      expect(adoptRequest).not.toHaveProperty('apiKey');

      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'happy-hare-result',
          requestId: adoptRequest.requestId,
          result: {
            ok: true,
            operation: 'adopt',
            physicalPrinterId: 12,
            materialSystemId: 34,
            adoptedGates: 1,
          },
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      await expect(adopting).resolves.toMatchObject({ ok: true, adoptedGates: 1 });
    } finally {
      unsubscribe();
      Object.defineProperty(window, 'parent', {
        configurable: true,
        value: originalParent,
      });
      window.history.pushState({}, '', '/');
    }
  });

  it('keeps Bambu LAN details out of the material confirmation bridge', async () => {
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
          capabilities: ['bambu-material-write'],
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      const expectedDesiredAssignments = [{
        slot: 0,
        preset_id: 41,
        spool_id: 301,
        source_ts: '2026-08-14T00:00:00Z',
      }];
      const pending = requestBambuMaterialAction(
        'apply',
        12,
        34,
        expectedDesiredAssignments,
      );
      const request = postMessage.mock.calls.at(-1)?.[0];

      expect(request).toMatchObject({
        source: PLUGIN_MESSAGE_SOURCE,
        type: 'bambu-material-apply',
        physicalPrinterId: 12,
        materialSystemId: 34,
        expectedDesiredAssignments,
      });
      expect(request).not.toHaveProperty('host');
      expect(request).not.toHaveProperty('accessCode');
      expect(request).not.toHaveProperty('serial');
      expect(request).not.toHaveProperty('command');
      expect(request).not.toHaveProperty('token');

      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'bambu-material-result',
          requestId: request.requestId,
          result: {
            ok: true,
            operation: 'apply',
            physicalPrinterId: 12,
            materialSystemId: 34,
            remainingChanges: [],
          },
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));

      await expect(pending).resolves.toMatchObject({ ok: true, remainingChanges: [] });
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
