import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  status: vi.fn(),
  issuePairingCode: vi.fn(),
  configure: vi.fn(),
  requestRefresh: vi.fn(),
  requestAssignment: vi.fn(),
  localSetup: undefined as undefined | ((state: {
    open: boolean;
    provider: 'bambu' | 'moonraker';
    physicalPrinterId?: number;
    materialSystemId?: number;
    outcome?: 'saved' | 'cancelled' | 'removed';
  }) => void),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
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
    callback(new Set(['bambu-lan-bridge', 'material-observation-refresh-v1']));
    return () => {};
  },
  configureBambuBridgeInPlugin: mocks.configure,
  requestBambuObservationRefresh: mocks.requestRefresh,
  requestBambuSlotAssignment: mocks.requestAssignment,
  subscribeToLocalPrinterSetup: (callback: NonNullable<typeof mocks.localSetup>) => {
    mocks.localSetup = callback;
    return () => { if (mocks.localSetup === callback) mocks.localSetup = undefined; };
  },
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

function show(autoConnect: boolean, connectionRef?: string, setupContext = context) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { client, ...render(
    <QueryClientProvider client={client}>
      {bambuAdapter.renderSetup?.({ ...setupContext, autoConnect, connectionRef })}
    </QueryClientProvider>,
  ) };
}

describe('Bambu setup', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.localSetup = undefined;
    mocks.requestRefresh.mockResolvedValue({
      ok: true,
      operation: 'refresh',
      physicalPrinterId: 11,
      materialSystemId: 21,
      observationUploaded: true,
    });
    mocks.status.mockResolvedValue({
      configured: false,
      paired: false,
      pairing_expires_at: null,
      last_seen_at: null,
      last_observation_at: null,
      last_snapshot_sequence: null,
      last_snapshot_source_instance_id: null,
      source_instance_id: null,
      node_instance_id: null,
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
    show(true, 'opaque-bambu-ref');

    await waitFor(() => expect(mocks.issuePairingCode).toHaveBeenCalledTimes(1));
    expect(mocks.issuePairingCode).toHaveBeenCalledWith(11, 21);
    await waitFor(() => expect(mocks.configure).toHaveBeenCalledWith(
      11,
      21,
      'Bambu Lab P2S',
      'FH-ABCDE-12345',
      'opaque-bambu-ref',
    ));
  });

  it('does not open local pairing automatically on an ordinary printer card', async () => {
    show(false);

    await waitFor(() => expect(mocks.status).toHaveBeenCalled());
    expect(mocks.issuePairingCode).not.toHaveBeenCalled();
    expect(mocks.configure).not.toHaveBeenCalled();
  });

  it('uses the printer status observation even when a stale bridge query still says unpaired', async () => {
    const receivedAt = new Date().toISOString();
    const setupContext = {
      ...context,
      printer: {
        ...context.printer,
        connectors: [{
          id: 31,
          material_system_id: 21,
          provider: 'bambu',
          transport: 'orca_plugin_lan',
          capabilities: ['read', 'presence'],
          active: true,
          last_seen_at: receivedAt,
          status_observation: {
            source: 'bambu_lan',
            observed_at: receivedAt,
            received_at: receivedAt,
            state: 'idle',
            progress_percent: null,
            remaining_seconds: null,
            current_layer: null,
            total_layers: null,
            job_name: null,
            nozzle_temperature: null,
            nozzle_target_temperature: null,
            bed_temperature: null,
            bed_target_temperature: null,
            chamber_temperature: null,
            wifi_signal: null,
            error_code: null,
          },
        }],
      },
    };

    show(false, undefined, setupContext);

    expect(await screen.findByText('presetSlots.bambu.connected')).toBeInTheDocument();
    expect(screen.queryByText('presetSlots.bambu.notConnected')).not.toBeInTheDocument();
  });

  it('does not treat a paired heartbeat as a printer snapshot', async () => {
    mocks.status.mockResolvedValue({
      configured: true,
      paired: true,
      pairing_expires_at: null,
      last_seen_at: new Date().toISOString(),
      last_observation_at: null,
      last_snapshot_sequence: null,
      last_snapshot_source_instance_id: null,
      source_instance_id: 'local-source',
      node_instance_id: 'local-node',
      provider: 'bambu',
      transport: 'orca_plugin_lan',
      capabilities: ['read', 'presence'],
    });

    show(false);

    expect(await screen.findByText('presetSlots.bambu.awaitingFirstData')).toBeInTheDocument();
    expect(screen.queryByText('presetSlots.bambu.connected')).not.toBeInTheDocument();
    expect(screen.queryByText('deviceLink.lastData')).not.toBeInTheDocument();
  });

  it('reloads bridge and printer snapshots after the local setup is saved', async () => {
    const receivedAt = new Date().toISOString();
    const view = show(false);
    await screen.findByText('presetSlots.bambu.notConnected');
    const invalidate = vi.spyOn(view.client, 'invalidateQueries');
    mocks.status.mockResolvedValue({
      configured: true,
      paired: true,
      pairing_expires_at: null,
      last_seen_at: receivedAt,
      last_observation_at: receivedAt,
      last_snapshot_sequence: 1,
      last_snapshot_source_instance_id: 'local-source',
      source_instance_id: 'local-source',
      node_instance_id: 'local-node',
      provider: 'bambu',
      transport: 'orca_plugin_lan',
      capabilities: ['read', 'presence'],
    });

    act(() => mocks.localSetup?.({
      open: false,
      provider: 'bambu',
      physicalPrinterId: 11,
      materialSystemId: 21,
      outcome: 'saved',
    }));

    expect(await screen.findByText('presetSlots.bambu.connected')).toBeInTheDocument();
    expect(mocks.status).toHaveBeenCalledTimes(2);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['printer-bridge-status', 11, 21] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['physical-printers'] });
  });

  it('reports every reconciliation run without a preview or apply step', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { toast } = await import('../../Toast');
    const actionContext = {
      ...context,
      printer: {
        ...context.printer,
        connectors: [{
          id: 31,
          material_system_id: 21,
          provider: 'bambu',
          transport: 'orca_plugin_lan',
          active: true,
        }],
      },
    };
    render(
      <QueryClientProvider client={client}>
        {bambuAdapter.renderActions?.(actionContext)}
      </QueryClientProvider>,
    );

    const button = await screen.findByText('presetSlots.bambu.materials.check');
    fireEvent.click(button);

    await waitFor(() => expect(mocks.requestRefresh).toHaveBeenCalledWith(11, 21));
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(button).not.toBeDisabled());
    fireEvent.click(button);
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(2));
    expect(toast.success).toHaveBeenLastCalledWith(
      'presetSlots.bambu.materials.refreshed',
      undefined,
      'bambu-materials-11-21',
    );
    expect(screen.queryByText('presetSlots.bambu.materials.apply')).not.toBeInTheDocument();
  });
});
