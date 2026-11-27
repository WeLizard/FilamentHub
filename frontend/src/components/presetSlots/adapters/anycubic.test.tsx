import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MaterialSystem, PhysicalPrinter } from '../../../api/client';
import { anycubicAdapter } from './anycubic';
import { feedAdapterFor } from './index';

const { issuePairingCode, status, configure, refresh } = vi.hoisted(() => ({
  issuePairingCode: vi.fn(),
  status: vi.fn(),
  configure: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock('../../../api/client', () => ({
  printerBridgeAPI: { issuePairingCode, status },
  // Other adapters in the registry import these; this test never calls them.
  spoolAPI: {}, presetSlotAPI: {}, physicalPrinterAPI: {}, edgeAPI: {}, octoprintBridgeAPI: {},
}));

vi.mock('../../../utils/pluginBridge', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/pluginBridge')>()),
  isPluginEmbed: () => true,
  configureAnycubicBridgeInPlugin: configure,
  requestAnycubicObservationRefresh: refresh,
  requestPluginCapabilities: vi.fn(),
  subscribeToPluginCapabilities: vi.fn((callback) => {
    callback(new Set(['anycubic-lan-bridge']));
    return vi.fn();
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ i18n: { language: 'en' }, t: (key: string) => key }),
  Trans: () => null,
}));

const system = {
  id: 9, name: 'ACE', kind: 'mmu', provider: 'anycubic', capabilities: [], active: true,
  declared_slot_count: null, slots: [],
} as unknown as MaterialSystem;
const printer = {
  id: 7, name: 'Kobra S1', material_systems: [system], connectors: [],
} as unknown as PhysicalPrinter;

describe('Anycubic through OrcaSlicer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    status.mockResolvedValue({ paired: false, last_observation_at: null });
    issuePairingCode.mockResolvedValue({
      pairing_code: 'FH-ABCDE-12345', expires_at: new Date(Date.now() + 600_000).toISOString(),
    });
  });

  it('is the feed system an Anycubic card is shown with, not the direct-feed fallback', () => {
    expect(feedAdapterFor('anycubic')).toBe(anycubicAdapter);
    // An ACE card starts with four slots and the printer's own spool holder.
    const ace = anycubicAdapter.onboarding!.topologies[0];
    expect(ace.slots(4).map((slot) => slot.provider_index)).toEqual([0, 1, 2, 3]);
    expect(ace.extras).toEqual([expect.objectContaining({ index: 255, kind: 'external', checked: true })]);
  });

  it('links through the plugin and explains a printer with LAN mode off', async () => {
    configure.mockResolvedValueOnce({ ok: false, code: 'lan_mode' });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}>
      {anycubicAdapter.renderSetup?.({ printer, system, gates: [], spools: [], linkConfirmed: false })}
    </QueryClientProvider>);

    fireEvent.click(await screen.findByText('presetSlots.anycubic.connect'));

    expect(await screen.findByRole('alert')).toHaveTextContent('presetSlots.anycubic.result.lan_mode');
    expect(configure).toHaveBeenCalledWith(7, 9, 'FH-ABCDE-12345', undefined);
    expect(refresh).not.toHaveBeenCalled();
  });
});
