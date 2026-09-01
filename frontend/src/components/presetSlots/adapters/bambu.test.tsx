import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  status: vi.fn(),
  issuePairingCode: vi.fn(),
  configure: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../../../api/client', () => ({
  printerBridgeAPI: {
    status: mocks.status,
    issuePairingCode: mocks.issuePairingCode,
  },
}));

vi.mock('../../../utils/pluginBridge', () => ({
  isPluginEmbed: () => true,
  requestPluginCapabilities: vi.fn(),
  subscribeToPluginCapabilities: (callback: (capabilities: Set<string>) => void) => {
    callback(new Set(['bambu-lan-bridge']));
    return () => {};
  },
  configureBambuBridgeInPlugin: mocks.configure,
  requestBambuMaterialAction: vi.fn(),
}));

vi.mock('../../Toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { bambuAdapter } from './bambu';

const context = {
  printer: {
    id: 11,
    name: 'Bambu Lab P2S',
    connectors: [],
  },
  system: {
    id: 21,
    provider: 'bambu',
    slots: [],
  },
  gates: [],
  spools: [],
  linkConfirmed: false,
} as any;

function show(autoConnect: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      {bambuAdapter.renderSetup?.({ ...context, autoConnect })}
    </QueryClientProvider>,
  );
}

describe('Bambu setup', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.status.mockResolvedValue({
      configured: false,
      paired: false,
      pairing_expires_at: null,
      last_seen_at: null,
      provider: 'bambu',
      transport: 'orca_plugin_lan',
      capabilities: [],
    });
    mocks.issuePairingCode.mockResolvedValue({
      pairing_code: 'FH-ABCDE-12345',
      expires_at: '2026-09-01T22:00:00Z',
    });
  });

  it('starts local pairing once immediately after the wizard saves a Bambu printer', async () => {
    show(true);

    await waitFor(() => expect(mocks.issuePairingCode).toHaveBeenCalledTimes(1));
    expect(mocks.issuePairingCode).toHaveBeenCalledWith(11, 21);
    await waitFor(() => expect(mocks.configure).toHaveBeenCalledWith(
      11,
      21,
      'Bambu Lab P2S',
      'FH-ABCDE-12345',
    ));
  });

  it('does not open local pairing automatically on an ordinary printer card', async () => {
    show(false);

    await waitFor(() => expect(mocks.status).toHaveBeenCalled());
    expect(mocks.issuePairingCode).not.toHaveBeenCalled();
    expect(mocks.configure).not.toHaveBeenCalled();
  });
});
