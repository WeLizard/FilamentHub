import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MaterialSystem, PhysicalPrinter } from '../../../api/client';
import { flashforgeAdapter } from './flashforge';

const { issuePairingCode, status, configure, refresh, bridge } = vi.hoisted(() => ({
  issuePairingCode: vi.fn(),
  status: vi.fn(),
  configure: vi.fn(),
  refresh: vi.fn(),
  bridge: { embedded: true },
}));

vi.mock('../../../api/client', () => ({ printerBridgeAPI: { issuePairingCode, status } }));

vi.mock('../../../utils/pluginBridge', () => ({
  isPluginEmbed: () => bridge.embedded,
  configureFlashforgeBridgeInPlugin: configure,
  requestFlashforgeObservationRefresh: refresh,
  requestPluginCapabilities: vi.fn(),
  subscribeToPluginCapabilities: vi.fn((callback) => {
    callback(new Set(['flashforge-lan-bridge']));
    return vi.fn();
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ i18n: { language: 'en' }, t: (key: string) => key }),
}));

const system = {
  id: 9, name: 'Station', kind: 'mmu', provider: 'flashforge', capabilities: [], active: true,
  declared_slot_count: null, slots: [],
} as unknown as MaterialSystem;
const printer = {
  id: 7, name: 'Creator 5 Pro', material_systems: [system], connectors: [],
} as unknown as PhysicalPrinter;

function show(target: PhysicalPrinter = printer) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>
    {flashforgeAdapter.renderSetup?.({ printer: target, system, gates: [], spools: [], linkConfirmed: false })}
  </QueryClientProvider>);
}

describe('Flashforge through OrcaSlicer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    bridge.embedded = true;
    status.mockResolvedValue({ paired: false, last_observation_at: null });
    issuePairingCode.mockResolvedValue({
      pairing_code: 'FH-ABCDE-12345', expires_at: new Date(Date.now() + 600_000).toISOString(),
    });
  });

  it('lets the person pick among several printers without spending a second pairing code', async () => {
    configure
      .mockResolvedValueOnce({ ok: false, code: 'choose', candidates: [
        { connectionRef: 'ff_a', label: 'Creator 5 Pro 0.4' },
        { connectionRef: 'ff_b', label: 'AD5X' },
      ] })
      .mockResolvedValueOnce({ ok: false, code: 'auth' });
    show();

    fireEvent.click(await screen.findByText('presetSlots.flashforge.connect'));
    fireEvent.click(await screen.findByText('AD5X'));

    // The printer's own refusal is explained; nothing is asked of the person here.
    expect(await screen.findByRole('alert')).toHaveTextContent('presetSlots.flashforge.result.auth');
    expect(issuePairingCode).toHaveBeenCalledTimes(1);
    expect(configure).toHaveBeenNthCalledWith(1, 7, 9, 'FH-ABCDE-12345', undefined);
    expect(configure).toHaveBeenNthCalledWith(2, 7, 9, 'FH-ABCDE-12345', 'ff_b');
  });

  it('reads a linked printer once when the card opens and never on a timer', async () => {
    status.mockResolvedValue({ paired: true, last_observation_at: null });
    refresh.mockResolvedValue({ ok: true, code: 'ok' });
    show();

    await waitFor(() => expect(refresh).toHaveBeenCalledWith(7, 9));
    await screen.findByText('presetSlots.flashforge.refresh');
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(configure).not.toHaveBeenCalled();
  });

  it('stays out of the way in a browser when the printer is linked only through Edge', () => {
    bridge.embedded = false;
    const { container } = show({ ...printer, connectors: [{
      provider: 'flashforge', transport: 'edge_agent', material_system_id: 9,
    }] } as unknown as PhysicalPrinter);

    expect(container).toBeEmptyDOMElement();
    expect(status).not.toHaveBeenCalled();
  });
});
