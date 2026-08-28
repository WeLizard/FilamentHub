import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MaterialSystem, PhysicalPrinter, PrinterBridgeStatus } from '../../../api/client';
import { happyHareAdapter } from './happyHare';

const { issuePairingCode, status } = vi.hoisted(() => ({
  issuePairingCode: vi.fn(),
  status: vi.fn(),
}));

vi.mock('../../../api/client', () => ({
  devicesAPI: { update: vi.fn() },
  printerBridgeAPI: { issuePairingCode, status },
}));

vi.mock('../../../utils/pluginBridge', () => ({
  isPluginEmbed: () => false,
  requestHappyHareAction: vi.fn(),
  requestPluginCapabilities: vi.fn(),
  subscribeToPluginCapabilities: vi.fn(() => vi.fn()),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string) => key,
  }),
}));

const system: MaterialSystem = {
  id: 20,
  name: 'ERCF',
  kind: 'mmu',
  provider: 'happy_hare',
  capabilities: ['read', 'write'],
  active: true,
  declared_slot_count: null,
  slots: [],
};

const printer: PhysicalPrinter = {
  id: 10,
  logical_id: 'printer-10',
  printer_id: null,
  name: 'Voron',
  printer_profile_ids: [],
  material_systems: [system],
  connectors: [],
  has_api_key: false,
  printer_hostname: 'voron',
  reports_feed: false,
  last_seen_at: null,
  created_at: '2026-08-28T00:00:00Z',
  updated_at: '2026-08-28T00:00:00Z',
};

function bridgeStatus(overrides: Partial<PrinterBridgeStatus> = {}): PrinterBridgeStatus {
  return {
    configured: false,
    paired: false,
    pairing_expires_at: null,
    last_seen_at: null,
    last_observation_at: null,
    last_snapshot_sequence: null,
    last_snapshot_source_instance_id: null,
    source_instance_id: null,
    provider: 'happy_hare',
    transport: 'edge_agent',
    capabilities: [],
    ...overrides,
  };
}

function renderSetup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const setup = happyHareAdapter.renderSetup?.({
    printer,
    system,
    gates: [],
    spools: [],
    linkConfirmed: false,
  });
  return render(
    <QueryClientProvider client={queryClient}>{setup}</QueryClientProvider>,
  );
}

describe('Happy Hare Edge setup', () => {
  beforeEach(() => {
    issuePairingCode.mockReset();
    status.mockReset();
  });

  it('uses the isolated Edge transport and shows the one-time pairing code', async () => {
    const expiresAt = new Date(Date.now() + 10 * 60_000).toISOString();
    status
      .mockResolvedValueOnce(bridgeStatus())
      .mockResolvedValue(bridgeStatus({ pairing_expires_at: expiresAt }));
    issuePairingCode.mockResolvedValue({
      pairing_code: 'FH-ABCDE-12345',
      expires_at: expiresAt,
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    renderSetup();

    await waitFor(() => {
      expect(status).toHaveBeenCalledWith(10, 20, 'edge_agent');
    });
    const createButton = await screen.findByText('presetSlots.happyHare.edge.createCode');
    await waitFor(() => expect(createButton).not.toBeDisabled());
    fireEvent.click(createButton);

    expect(await screen.findByText('FH-ABCDE-12345')).toBeInTheDocument();
    expect(issuePairingCode).toHaveBeenCalledWith(10, 20, 'edge_agent');
    expect(screen.getByText('presetSlots.happyHare.edge.codeHint')).toBeInTheDocument();

    fireEvent.click(screen.getByText('presetSlots.happyHare.edge.copyCode'));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('FH-ABCDE-12345'));
  });

  it('reports a paired Edge separately from the local Happy Hare credentials', async () => {
    status.mockResolvedValue(bridgeStatus({
      configured: true,
      paired: true,
      last_seen_at: '2026-08-28T12:00:00Z',
      last_observation_at: '2026-08-28T11:59:59Z',
      source_instance_id: 'edge-instance-1234567890',
    }));

    renderSetup();

    expect(await screen.findByText('presetSlots.happyHare.edge.connected')).toBeInTheDocument();
    expect(screen.getByText('presetSlots.happyHare.edge.lastContact')).toBeInTheDocument();
    expect(screen.queryByText(/moonraker_url|moonraker_api_key/i)).not.toBeInTheDocument();
  });

  it('keeps the one-time code visible when the follow-up status check fails', async () => {
    status
      .mockResolvedValueOnce(bridgeStatus())
      .mockRejectedValueOnce(new Error('status unavailable'));
    issuePairingCode.mockResolvedValue({
      pairing_code: 'FH-SAFE1-RETRY',
      expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
    });

    renderSetup();

    const createButton = await screen.findByText('presetSlots.happyHare.edge.createCode');
    await waitFor(() => expect(createButton).not.toBeDisabled());
    fireEvent.click(createButton);
    expect(await screen.findByText('FH-SAFE1-RETRY')).toBeInTheDocument();
    expect(screen.getByText('presetSlots.happyHare.edge.statusUnavailable')).toBeInTheDocument();
  });
});
