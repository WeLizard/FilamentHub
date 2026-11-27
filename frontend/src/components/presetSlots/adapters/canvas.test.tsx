import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MaterialSystem, PhysicalPrinter } from '../../../api/client';
import type { Printer } from '../../../types/api';
import { EdgeConnectionSetup } from '../EdgeConnectionSetup';
import { elegooMqttAdapter } from './elegooMqtt';
import { feedAdapterFor, setupAdaptersFor, supportsEdgeSetup } from './index';
import { sdcpAdapter } from './sdcp';

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
  configureProfileLanBridgeInPlugin: configure,
  requestProfileLanObservationRefresh: refresh,
  requestPluginCapabilities: vi.fn(),
  subscribeToPluginCapabilities: vi.fn((callback) => {
    callback(new Set(['sdcp-lan-bridge', 'elegoo_mqtt-lan-bridge']));
    return vi.fn();
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ i18n: { language: 'en' }, t: (key: string) => key }),
  Trans: () => null,
}));

const elegoo = (model: string) => ({ manufacturer: 'Elegoo', model, name: `Elegoo ${model}` } as Printer);

function renderSetup(provider: 'sdcp' | 'elegoo_mqtt') {
  const system = {
    id: 9, name: 'CANVAS', kind: 'mmu', provider, capabilities: [], active: true,
    declared_slot_count: null, slots: [],
  } as unknown as MaterialSystem;
  const printer = {
    id: 7, name: 'Centauri Carbon', material_systems: [system], connectors: [],
  } as unknown as PhysicalPrinter;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>
    {feedAdapterFor(provider).renderSetup?.({ printer, system, gates: [], spools: [], linkConfirmed: false })}
  </QueryClientProvider>);
}

describe('CANVAS printers through OrcaSlicer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    status.mockResolvedValue({ paired: false, last_observation_at: null });
    issuePairingCode.mockResolvedValue({
      pairing_code: 'FH-ABCDE-12345', expires_at: new Date(Date.now() + 600_000).toISOString(),
    });
  });

  it.each([sdcpAdapter, elegooMqttAdapter])('$id is the feed system its cards are shown with', (adapter) => {
    expect(feedAdapterFor(adapter.id)).toBe(adapter);
    // With a CANVAS the printer lists only its slots; without one, its spool holder.
    const [canvas, single] = adapter.onboarding!.topologies;
    expect(canvas.slots(8).map((slot) => slot.provider_index)).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
    expect(canvas.count?.max).toBe(16);
    expect(single.slots(0)).toEqual([{ provider_index: 255, kind: 'external' }]);
  });

  it('offers SDCP for a Centauri Carbon, the MQTT API for a Carbon 2, neither for Klipper', () => {
    expect(setupAdaptersFor(elegoo('Centauri Carbon'))).toEqual([sdcpAdapter]);
    expect(setupAdaptersFor(elegoo('Centauri Carbon 2'))).toEqual([elegooMqttAdapter]);
    for (const adapter of [sdcpAdapter, elegooMqttAdapter]) {
      expect(adapter.onboarding!.matchesModel!(elegoo('Neptune 4 Pro'))).toBe(false);
    }
  });

  it.each([
    ['sdcp', 'AddToNodeSdcp', false],
    ['elegoo_mqtt', 'AddToNodeElegooMqtt', true],
  ] as const)('gives FH Edge a %s entry without any address or code of the printer', async (provider, text, code) => {
    expect(supportsEdgeSetup(provider, 'mmu')).toBe(true);
    expect(supportsEdgeSetup(provider, 'direct_feed')).toBe(true);
    const system = { id: 9, name: 'CANVAS', kind: 'mmu', provider, capabilities: [], active: true,
      declared_slot_count: null, slots: [] } as unknown as MaterialSystem;
    const printer = { id: 7, name: 'Carbon', material_systems: [system], connectors: [] } as unknown as PhysicalPrinter;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><EdgeConnectionSetup printer={printer} system={system} /></QueryClientProvider>);

    const create = await screen.findByText('presetSlots.edge.createCode');
    await waitFor(() => expect(create.closest('button')).toBeEnabled());
    fireEvent.click(create);

    const entry = JSON.parse((await screen.findByText(/"adapter"/)).textContent ?? '{}');
    expect(entry).toEqual({
      id: 'printer-7', name: 'Carbon', adapter: provider, printer_url: 'PRINTER-LAN-IP',
      ...(code ? { access_code: 'ACCESS-CODE-FROM-PRINTER' } : {}),
      pairing_code: 'FH-ABCDE-12345',
    });
    expect(screen.getByText(`presetSlots.edge.${text[0].toLowerCase()}${text.slice(1)}`)).toBeInTheDocument();
  });

  it.each([
    ['sdcp', 'presetSlots.sdcp'],
    ['elegoo_mqtt', 'presetSlots.elegooMqtt'],
  ] as const)('links %s through the plugin with its own wording', async (provider, text) => {
    configure.mockResolvedValueOnce({ ok: false, code: 'identity' });
    renderSetup(provider);

    fireEvent.click(await screen.findByText(`${text}.connect`));

    expect(await screen.findByRole('alert')).toHaveTextContent(`${text}.result.identity`);
    expect(configure).toHaveBeenCalledWith(provider, 7, 9, 'FH-ABCDE-12345', undefined);
    expect(refresh).not.toHaveBeenCalled();
  });
});
