import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MaterialSystem, PhysicalPrinter } from '../../../api/client';
import { prusaLinkAdapter } from './prusalink';
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
  configurePrusaLinkBridgeInPlugin: configure,
  requestPrusaLinkObservationRefresh: refresh,
  requestPluginCapabilities: vi.fn(),
  subscribeToPluginCapabilities: vi.fn((callback) => {
    callback(new Set(['prusalink-lan-bridge']));
    return vi.fn();
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ i18n: { language: 'en' }, t: (key: string) => key }),
  Trans: () => null,
}));

const system = {
  id: 9, name: 'Spool', kind: 'direct_feed', provider: 'prusalink', capabilities: [], active: true,
  declared_slot_count: null, slots: [],
} as unknown as MaterialSystem;
const printer = {
  id: 7, name: 'MK4S', material_systems: [system], connectors: [],
} as unknown as PhysicalPrinter;

describe('Prusa through OrcaSlicer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    status.mockResolvedValue({ paired: false, last_observation_at: null });
    issuePairingCode.mockResolvedValue({
      pairing_code: 'FH-ABCDE-12345', expires_at: new Date(Date.now() + 600_000).toISOString(),
    });
  });

  it('is offered for Prusa printers and describes a single spool, the MMU3 and XL tools', () => {
    expect(feedAdapterFor('prusalink')).toBe(prusaLinkAdapter);
    const onboarding = prusaLinkAdapter.onboarding!;
    const matches = onboarding.matchesModel!;
    const model = (manufacturer: string) => ({ manufacturer }) as Parameters<typeof matches>[0];
    expect(matches(model('Prusa Research'))).toBe(true);
    expect(matches(model('Prusa'))).toBe(true);
    expect(matches(model('Creality'))).toBe(false);
    const [single, mmu3, tools] = onboarding.topologies;
    expect(single.slots(1)).toEqual([{ provider_index: 0, kind: 'external' }]);
    expect(mmu3.slots(5).map((slot) => slot.provider_index)).toEqual([0, 1, 2, 3, 4]);
    expect(tools.slots(2)).toEqual([
      { provider_index: 0, kind: 'tool' }, { provider_index: 1, kind: 'tool' },
    ]);
    // The local API cannot set a material, so the site never offers to write one.
    expect(prusaLinkAdapter.capabilities).toEqual(['read', 'presence']);
  });

  it('links through the plugin and explains firmware without a serial number', async () => {
    configure.mockResolvedValueOnce({ ok: false, code: 'firmware' });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}>
      {prusaLinkAdapter.renderSetup?.({ printer, system, gates: [], spools: [], linkConfirmed: false })}
    </QueryClientProvider>);

    fireEvent.click(await screen.findByText('presetSlots.prusalink.connect'));

    expect(await screen.findByRole('alert')).toHaveTextContent('presetSlots.prusalink.result.firmware');
    expect(configure).toHaveBeenCalledWith(7, 9, 'FH-ABCDE-12345', undefined);
    expect(refresh).not.toHaveBeenCalled();
  });
});
