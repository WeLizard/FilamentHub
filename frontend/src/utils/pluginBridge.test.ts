import { describe, expect, it, vi } from 'vitest';

import {
  configureBambuBridgeInPlugin,
  importPresetToPlugin,
  installPrinterBundleInPlugin,
  removePrinterBundleFromPlugin,
  PLUGIN_MESSAGE_SOURCE,
  reportPluginSessionToPlugin,
  requestBambuMaterialAction,
  requestBambuObservationRefresh,
  requestBambuSlotAssignment,
  requestHappyHareAction,
  requestHappyHareSlotAssignment,
  requestPluginProfileSync,
  requestPluginCapabilities,
  requestPrinterSetup,
  requestInstalledPrinterBundles,
  subscribeToPluginCapabilities,
  subscribeToLocalPrinterSetup,
  subscribeToPluginNavigation,
  subscribeToPluginRecoverList,
} from './pluginBridge';

describe('pluginBridge inbound messages', () => {
  it('accepts only trusted local setup lifecycle fields', () => {
    const originalParent = window.parent;
    const parent = { postMessage: vi.fn() };
    Object.defineProperty(window, 'parent', { configurable: true, value: parent });
    window.history.pushState({}, '', '/embed/profile');
    const onState = vi.fn();
    const unsubscribe = subscribeToLocalPrinterSetup(onState);
    const validBambu = {
      source: PLUGIN_MESSAGE_SOURCE,
      type: 'local-printer-setup-state',
      open: false,
      provider: 'bambu',
      physicalPrinterId: 11,
      materialSystemId: 21,
      outcome: 'saved',
      host: '192.0.2.10',
      accessCode: 'local-secret',
      code: 'pairing-secret',
    };
    const dispatch = (data: unknown, origin = window.location.origin, source: MessageEventSource = parent as unknown as Window) => {
      window.dispatchEvent(new MessageEvent('message', { data, origin, source }));
    };

    try {
      dispatch(validBambu, 'https://evil.example');
      dispatch(validBambu, window.location.origin, window);
      dispatch({ ...validBambu, source: 'untrusted-source' });
      dispatch({ ...validBambu, provider: 'octoprint' });
      dispatch({ ...validBambu, physicalPrinterId: 0 });
      dispatch({ ...validBambu, materialSystemId: -1 });
      expect(onState).not.toHaveBeenCalled();

      dispatch({
        ...validBambu,
        open: true,
        provider: 'moonraker',
        physicalPrinterId: 99,
        materialSystemId: 100,
        outcome: 'saved',
      });
      dispatch(validBambu);

      expect(onState.mock.calls.map(([state]) => state)).toEqual([{
        open: true,
        provider: 'moonraker',
      }, {
        open: false,
        provider: 'bambu',
        physicalPrinterId: 11,
        materialSystemId: 21,
        outcome: 'saved',
      }]);
      expect(JSON.stringify(onState.mock.calls)).not.toMatch(/host|accessCode|pairing-secret|local-secret/);
    } finally {
      unsubscribe();
      Object.defineProperty(window, 'parent', { configurable: true, value: originalParent });
      window.history.pushState({}, '', '/');
    }
  });

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
          capabilities: [
            'profile-sync-scopes-v1',
            'printer-bundle-result-v1',
            'printer-bundle-toggle-v1',
          ],
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

      const removing = removePrinterBundleFromPlugin(7);
      const removeRequest = postMessage.mock.calls.at(-1)?.[0];
      expect(removeRequest).toMatchObject({
        type: 'remove-printer-bundle',
        physicalPrinterId: 7,
      });
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'printer-bundle-result',
          requestId: removeRequest.requestId,
          status: 'success',
          text: 'bundle removed',
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      await expect(removing).resolves.toEqual({ message: 'bundle removed' });

      const readingStatus = requestInstalledPrinterBundles([7, 8, 8]);
      const statusRequest = postMessage.mock.calls.at(-1)?.[0];
      expect(statusRequest).toMatchObject({
        type: 'printer-bundle-status',
        physicalPrinterIds: [7, 8],
      });
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'printer-bundle-status-result',
          requestId: statusRequest.requestId,
          status: 'success',
          installedPrinterIds: [7, '8', true, -1],
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      await expect(readingStatus).resolves.toEqual(new Set([7]));
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
      configureBambuBridgeInPlugin(12, 34, 'Workshop X1C', 'FH-ABCDE-12345', 'opaque-bambu-ref');
      expect(postMessage.mock.calls.at(-1)?.[0]).toEqual({
        source: PLUGIN_MESSAGE_SOURCE,
        type: 'configure-bambu',
        physicalPrinterId: 12,
        materialSystemId: 34,
        printerName: 'Workshop X1C',
        pairingCode: 'FH-ABCDE-12345',
        connectionRef: 'opaque-bambu-ref',
      });
      expect(postMessage.mock.calls.at(-1)?.[0]).not.toHaveProperty('host');
      expect(postMessage.mock.calls.at(-1)?.[0]).not.toHaveProperty('accessCode');
      expect(postMessage.mock.calls.at(-1)?.[0]).not.toHaveProperty('serial');

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

  it('sends only the exact committed slot for immediate material delivery', async () => {
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
          capabilities: ['material-assignment-v1', 'material-observation-refresh-v1'],
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      const commit = {
        materialSlotId: 91,
        providerIndex: 5,
        assignmentRevision: 12,
        desired: {
          presetId: 41,
          spoolId: 301,
          sourceTs: '2026-09-05T12:00:00Z',
        },
      };
      const pending = requestBambuSlotAssignment(12, 34, commit);
      const request = postMessage.mock.calls.at(-1)?.[0];

      expect(request).toEqual({
        source: PLUGIN_MESSAGE_SOURCE,
        type: 'bambu-material-assign',
        requestId: expect.any(String),
        physicalPrinterId: 12,
        materialSystemId: 34,
        commit,
      });
      expect(JSON.stringify(request)).not.toMatch(/host|accessCode|serial|color|command|token/i);
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'bambu-material-result',
          requestId: request.requestId,
          result: {
            ok: true,
            operation: 'assign',
            physicalPrinterId: 12,
            materialSystemId: 34,
            applied: true,
            observationUploaded: true,
          },
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      await expect(pending).resolves.toMatchObject({ ok: true, applied: true });

      const hhPending = requestHappyHareSlotAssignment(20, 21, commit);
      const hhRequest = postMessage.mock.calls.at(-1)?.[0];
      expect(hhRequest).toMatchObject({
        type: 'happy-hare-material-assign',
        physicalPrinterId: 20,
        materialSystemId: 21,
        commit,
      });
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'happy-hare-result',
          requestId: hhRequest.requestId,
          result: { ok: false, operation: 'assign', code: 'printer_busy',
            physicalPrinterId: 20, materialSystemId: 21 },
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      await expect(hhPending).resolves.toMatchObject({ ok: false, code: 'printer_busy' });

      const refreshPending = requestBambuObservationRefresh(12, 34);
      const refreshRequest = postMessage.mock.calls.at(-1)?.[0];
      expect(refreshRequest).toEqual({
        source: PLUGIN_MESSAGE_SOURCE,
        type: 'bambu-material-refresh',
        requestId: expect.any(String),
        physicalPrinterId: 12,
        materialSystemId: 34,
      });
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'bambu-material-result',
          requestId: refreshRequest.requestId,
          result: { ok: true, operation: 'refresh', physicalPrinterId: 12,
            materialSystemId: 34, observationUploaded: true },
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      await expect(refreshPending).resolves.toMatchObject({
        ok: true,
        observationUploaded: true,
      });
    } finally {
      unsubscribe();
      Object.defineProperty(window, 'parent', { configurable: true, value: originalParent });
      window.history.pushState({}, '', '/');
    }
  });

  it('rejects an immediate result for another operation or target', async () => {
    const originalParent = window.parent;
    const postMessage = vi.fn();
    const parent = { postMessage };
    Object.defineProperty(window, 'parent', { configurable: true, value: parent });
    window.history.pushState({}, '', '/embed/profile');
    const unsubscribe = subscribeToPluginCapabilities(() => undefined);

    try {
      window.dispatchEvent(new MessageEvent('message', {
        data: { source: PLUGIN_MESSAGE_SOURCE, type: 'plugin-capabilities',
          capabilities: ['material-observation-refresh-v1'] },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      const pending = requestBambuObservationRefresh(12, 34);
      const request = postMessage.mock.calls.at(-1)?.[0];
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'bambu-material-result',
          requestId: request.requestId,
          result: {
            ok: true,
            operation: 'assign',
            physicalPrinterId: 12,
            materialSystemId: 99,
            applied: 'yes',
          },
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));

      await expect(pending).rejects.toThrow('invalid material operation result');
    } finally {
      unsubscribe();
      Object.defineProperty(window, 'parent', { configurable: true, value: originalParent });
      window.history.pushState({}, '', '/');
    }
  });

  it('negotiates discovery and keeps a Moonraker probe open for local credential input', async () => {
    const originalParent = window.parent;
    const postMessage = vi.fn();
    const parent = { postMessage };
    Object.defineProperty(window, 'parent', { configurable: true, value: parent });
    window.history.pushState({}, '', '/embed/profile');
    const unsubscribe = subscribeToPluginCapabilities(() => undefined);
    vi.useFakeTimers();

    try {
      for (const discovery of [false, true]) {
        window.dispatchEvent(new MessageEvent('message', {
          data: { source: PLUGIN_MESSAGE_SOURCE, type: 'plugin-capabilities',
            capabilities: ['printer-setup-v1', ...(discovery ? ['printer-discovery-v1'] : [])] },
          origin: window.location.origin, source: parent as unknown as Window,
        }));
        const listing = requestPrinterSetup('list');
        const request = postMessage.mock.calls.at(-1)?.[0];
        expect(request.discovery).toBe(discovery ? true : undefined);
        window.dispatchEvent(new MessageEvent('message', {
          data: { source: PLUGIN_MESSAGE_SOURCE, type: 'printer-setup-result',
            requestId: request.requestId, result: { ok: true, candidates: [] } },
          origin: window.location.origin, source: parent as unknown as Window,
        }));
        await expect(listing).resolves.toEqual({ ok: true, candidates: [] });
      }
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'plugin-capabilities',
          capabilities: ['printer-setup-v1'],
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));

      const pending = requestPrinterSetup('probe', {
        connectionRef: 'opaque-moonraker-ref',
        copy: {
          title: 'Connect Moonraker',
          hint: 'Enter the missing API key',
          address: 'Address',
          apiKey: 'API key',
          submit: 'Check',
        },
      });
      const request = postMessage.mock.calls.at(-1)?.[0];
      expect(request).toMatchObject({
        type: 'printer-setup',
        operation: 'probe',
        connectionRef: 'opaque-moonraker-ref',
        copy: {
          title: 'Connect Moonraker',
          hint: 'Enter the missing API key',
          address: 'Address',
          apiKey: 'API key',
          submit: 'Check',
        },
      });

      let settled = false;
      void pending.then(() => { settled = true; }, () => { settled = true; });
      await vi.advanceTimersByTimeAsync(599_999);
      expect(settled).toBe(false);

      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: PLUGIN_MESSAGE_SOURCE,
          type: 'printer-setup-result',
          requestId: request.requestId,
          result: { ok: false, code: 'cancelled' },
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
      await expect(pending).resolves.toEqual({ ok: false, code: 'cancelled' });
    } finally {
      vi.useRealTimers();
      unsubscribe();
      Object.defineProperty(window, 'parent', { configurable: true, value: originalParent });
      window.history.pushState({}, '', '/');
    }
  });
});
