import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MaterialSystem, PhysicalPrinter } from '../../../api/client';
import { crealityAdapter } from './creality';
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
  configureCrealityBridgeInPlugin: configure,
  requestCrealityObservationRefresh: refresh,
  requestPluginCapabilities: vi.fn(),
  subscribeToPluginCapabilities: vi.fn((callback) => {
    callback(new Set(['creality-lan-bridge']));
    return vi.fn();
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ i18n: { language: 'en' }, t: (key: string) => key }),
  Trans: () => null,
}));

const system = {
  id: 9, name: 'CFS', kind: 'mmu', provider: 'creality', capabilities: [], active: true,
  declared_slot_count: null, slots: [],
} as unknown as MaterialSystem;
const printer = {
  id: 7, name: 'K2 Plus', material_systems: [system], connectors: [],
} as unknown as PhysicalPrinter;

describe('Creality through OrcaSlicer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    status.mockResolvedValue({ paired: false, last_observation_at: null });
    issuePairingCode.mockResolvedValue({
      pairing_code: 'FH-ABCDE-12345', expires_at: new Date(Date.now() + 600_000).toISOString(),
    });
  });

  it('is the feed system a Creality card is shown with, not the direct-feed fallback', () => {
    expect(feedAdapterFor('creality')).toBe(crealityAdapter);
    // A CFS card starts with four slots and the printer's own spool holder.
    const cfs = crealityAdapter.onboarding!.topologies[0];
    expect(cfs.slots(4).map((slot) => slot.provider_index)).toEqual([0, 1, 2, 3]);
    expect(cfs.extras).toEqual([expect.objectContaining({ index: 255, kind: 'external', checked: true })]);
  });

  it('links through the plugin and explains a printer that cannot be told apart', async () => {
    configure.mockResolvedValueOnce({ ok: false, code: 'identity' });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}>
      {crealityAdapter.renderSetup?.({ printer, system, gates: [], spools: [], linkConfirmed: false })}
    </QueryClientProvider>);

    fireEvent.click(await screen.findByText('presetSlots.creality.connect'));

    expect(await screen.findByRole('alert')).toHaveTextContent('presetSlots.creality.result.identity');
    expect(configure).toHaveBeenCalledWith(7, 9, 'FH-ABCDE-12345', undefined);
    expect(refresh).not.toHaveBeenCalled();
  });
});
