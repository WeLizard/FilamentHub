import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MaterialSystem, PhysicalPrinter } from '../../../api/client';
import { flashforgeAdapter } from './flashforge';

const { issuePairingCode, status, configure, refresh, assign, bridge } = vi.hoisted(() => ({
  issuePairingCode: vi.fn(),
  status: vi.fn(),
  configure: vi.fn(),
  refresh: vi.fn(),
  assign: vi.fn(),
  bridge: { embedded: true },
}));

vi.mock('../../../api/client', () => ({ printerBridgeAPI: { issuePairingCode, status } }));

vi.mock('../../../utils/pluginBridge', () => ({
  isPluginEmbed: () => bridge.embedded,
  configureFlashforgeBridgeInPlugin: configure,
  requestFlashforgeObservationRefresh: refresh,
  requestFlashforgeSlotAssignment: assign,
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

    // The printer's own refusal is explained, and the check code can be typed again.
    expect(await screen.findByRole('alert')).toHaveTextContent('presetSlots.flashforge.result.auth');
    expect(screen.getByLabelText('presetSlots.flashforge.secret.label')).toBeInTheDocument();
    expect(issuePairingCode).toHaveBeenCalledTimes(1);
    expect(configure).toHaveBeenNthCalledWith(1, 7, 9, 'FH-ABCDE-12345', undefined);
    expect(configure).toHaveBeenNthCalledWith(2, 7, 9, 'FH-ABCDE-12345', 'ff_b');
  });

  it('asks only for the check code the plugin could not find, for the same printer and code', async () => {
    configure
      .mockResolvedValueOnce({ ok: false, code: 'choose', candidates: [
        { connectionRef: 'ff_a', label: 'Creator 5 Pro 0.4' },
        { connectionRef: 'ff_b', label: 'AD5X' },
      ] })
      .mockResolvedValueOnce({ ok: false, code: 'check_code' })
      .mockResolvedValueOnce({ ok: true, code: 'ok' });
    show();

    fireEvent.click(await screen.findByText('presetSlots.flashforge.connect'));
    fireEvent.click(await screen.findByText('AD5X'));
    const field = await screen.findByLabelText('presetSlots.flashforge.secret.label');
    // Nothing to send until something is typed.
    expect(screen.getByText('presetSlots.flashforge.secret.submit').closest('button')).toBeDisabled();
    fireEvent.change(field, { target: { value: ' 9f8e7d6c ' } });
    fireEvent.click(screen.getByText('presetSlots.flashforge.secret.submit'));

    await waitFor(() => expect(configure).toHaveBeenCalledTimes(3));
    expect(configure).toHaveBeenNthCalledWith(3, 7, 9, 'FH-ABCDE-12345', 'ff_b', '9f8e7d6c');
    // The one-time code was not spent by the missing check code.
    expect(issuePairingCode).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByLabelText('presetSlots.flashforge.secret.label')).toBeNull());
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

  it('hands a saved assignment to the plugin only for a station linked through OrcaSlicer', async () => {
    const slot = {
      id: 501, provider_index: 1, assignment_revision: 4,
      assignment: { preset_id: null, spool_id: 12, source_ts: null },
    };
    const linked = { ...printer, connectors: [{
      provider: 'flashforge', transport: 'orca_plugin_lan', material_system_id: 9, active: true,
    }] } as unknown as PhysicalPrinter;
    const deliver = (target: PhysicalPrinter, feed: MaterialSystem = system) => (
      flashforgeAdapter.deliverAssignment!({ printer: target, system: feed, slot } as never)
    );

    assign.mockResolvedValueOnce({ ok: true, code: 'ok' });
    await expect(deliver(linked)).resolves.toEqual({ status: 'delivered' });
    expect(assign).toHaveBeenCalledWith(7, 9, {
      materialSlotId: 501, providerIndex: 1, assignmentRevision: 4,
      desired: { presetId: null, spoolId: 12, sourceTs: null },
    });

    // The printer cannot name the spool's material: saved, and the reason is kept.
    assign.mockResolvedValueOnce({ ok: false, code: 'material_unsupported' });
    await expect(deliver(linked)).resolves.toEqual({
      status: 'saved_only', code: 'material_unsupported', physicallyApplied: false,
    });

    // Edge sets no slots, a single spool has none, and a browser holds no connection.
    assign.mockClear();
    await expect(deliver(printer)).resolves.toBeNull();
    await expect(deliver(linked, { ...system, kind: 'direct_feed' } as MaterialSystem)).resolves.toBeNull();
    bridge.embedded = false;
    await expect(deliver(linked)).resolves.toBeNull();
    expect(assign).not.toHaveBeenCalled();
  });
});
