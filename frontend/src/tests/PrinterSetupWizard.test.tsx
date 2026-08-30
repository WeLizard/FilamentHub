import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PrinterSetupWizard } from '../components/PrinterSetupWizard';
import type { PhysicalPrinter } from '../api/client';

const mocks = vi.hoisted(() => ({
  create: vi.fn(), setup: vi.fn(), plugin: vi.fn(), key: vi.fn(), embed: false,
  printers: vi.fn(), models: vi.fn(), model: vi.fn(), installed: vi.fn(),
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 1 } }) }));
vi.mock('../api/client', () => ({
  physicalPrintersAPI: { create: mocks.create, setupConnection: mocks.setup,
    list: mocks.printers, listInstalledCandidates: mocks.installed, listBindings: async () => [] },
  printersAPI: { list: mocks.models, get: mocks.model }, devicesAPI: { regenerateKey: mocks.key },
}));
vi.mock('../utils/pluginBridge', () => ({
  isPluginEmbed: () => mocks.embed, requestPrinterSetup: mocks.plugin,
  requestPluginCapabilities: vi.fn(),
  subscribeToPluginCapabilities: (cb: (caps: Set<string>) => void) => {
    cb(new Set(['printer-setup-v1'])); return () => {};
  },
}));
vi.mock('../components/presetSlots/adapters', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../components/presetSlots/adapters')>();
  return { ...actual, feedAdapterFor: (id: string) => ({ ...actual.feedAdapterFor(id),
    renderSetup: () => <div data-testid="adapter-setup">{id}</div> }) };
});
vi.mock('../components/presetSlots/EdgeConnectionSetup', () => ({ EdgeConnectionSetup: () => <div>edge-setup</div> }));

const saved = { id: 7, name: 'Workshop', printer_profile_ids: [], material_systems: [], connectors: [] } as unknown as PhysicalPrinter;
const probe = { ok: true, probeId: 'probe-1', provider: 'happy_hare', gateCount: 4,
  connection: { source_instance_id: 'local-desktop-source', connection_ref: 'ref-1',
    origin: 'orca_profile', provider: 'moonraker', endpoint_token: 'a'.repeat(64) } };

function show(physicalPrinter?: PhysicalPrinter, initialPrinterId?: number) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { client, ...render(<QueryClientProvider client={client}>
    <PrinterSetupWizard onClose={vi.fn()} physicalPrinter={physicalPrinter} initialPrinterId={initialPrinterId} />
  </QueryClientProvider>) };
}
async function namePrinter() {
  await waitFor(() => expect(screen.getByText('printerSetup.newDevice')).not.toBeDisabled());
  fireEvent.click(screen.getByText('printerSetup.newDevice'));
  fireEvent.change(screen.getByLabelText('printerSetup.name'), { target: { value: 'Workshop' } });
  fireEvent.click(screen.getByText('printerSetup.connectionOptional'));
}
function chooseMoonraker() {
  fireEvent.focus(screen.getByLabelText('printerSetup.connectionType'));
  fireEvent.click(screen.getByText('printerSetup.connections.moonraker'));
}
function savePrinter() {
  fireEvent.click(screen.getByRole('button', { name: /^printerSetup\.(save|connect)$/ }));
}

describe('PrinterSetupWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks(); localStorage.clear(); sessionStorage.clear(); mocks.embed = false;
    window.history.replaceState({}, '');
    mocks.create.mockResolvedValue(saved); mocks.setup.mockResolvedValue(saved);
    mocks.printers.mockResolvedValue([]); mocks.models.mockResolvedValue({ items: [] }); mocks.installed.mockResolvedValue([]);
    mocks.model.mockResolvedValue(null);
  });
  it('creates a usable manual printer and feed system without a plugin or Edge', async () => {
    show();
    expect(screen.getByText('printerSetup.target')).toBeInTheDocument();
    expect(screen.queryByText('printerSetup.routes.edge')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('printerSetup.feedSystem')).not.toBeInTheDocument();
    await namePrinter();
    expect(screen.getByText('printerSetup.manualHint')).toBeInTheDocument();
    savePrinter();
    await screen.findByText('printerSetup.saved');
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Workshop', request_id: expect.any(String),
      material_system: expect.objectContaining({ provider: 'manual', slot_count: 1 }),
    }));
    expect(mocks.plugin).not.toHaveBeenCalled(); expect(mocks.key).not.toHaveBeenCalled();
  });
  it('reopens and retries the exact unacknowledged request', async () => {
    mocks.create.mockRejectedValueOnce(new Error('response lost'));
    mocks.create.mockResolvedValueOnce({ ...saved, material_systems: [{ provider: 'manual' }] });
    const view = show(); await namePrinter();
    chooseMoonraker();
    fireEvent.click(screen.getByText('printerSetup.routes.edge'));
    fireEvent.click(screen.getByText('printerSetup.save'));
    await screen.findByRole('alert');
    const payload = mocks.create.mock.calls[0][0];
    view.unmount(); show();
    expect(screen.getByText('printerSetup.resume')).toBeInTheDocument();
    expect(screen.getByText('printerSetup.routes.edge')).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByText('printerSetup.resumeButton'));
    await screen.findByText('printerSetup.saved');
    expect(mocks.create.mock.calls[1][0]).toEqual(payload);
    expect(localStorage.getItem('fh-printer-setup-1')).toBeNull();
    expect(window.history.state.fhPrinterSetup).toBeUndefined();
    expect(screen.getByText('edge-setup')).toBeInTheDocument();
  });
  it('still saves when embedded browser storage is denied', async () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Blocked', 'SecurityError');
    });
    try {
      show(); await namePrinter(); savePrinter();
      await screen.findByText('printerSetup.saved');
      expect(mocks.create).toHaveBeenCalledTimes(1);
    } finally { storage.mockRestore(); }
  });
  it('does not send creation when neither storage nor history can retain the request', async () => {
    const deny = () => { throw new DOMException('Blocked', 'SecurityError'); };
    const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(deny);
    const history = vi.spyOn(window.history, 'replaceState').mockImplementation(deny);
    try {
      show(); await namePrinter(); savePrinter();
      expect(await screen.findByRole('alert')).toHaveTextContent('printerSetup.recoveryUnavailable');
      expect(mocks.create).not.toHaveBeenCalled();
      expect(screen.queryByText('printerSetup.resume')).not.toBeInTheDocument();
    } finally { storage.mockRestore(); history.mockRestore(); }
  });
  it('does not offer Edge for an unsupported existing feed system or block manual tracking', async () => {
    show({ ...saved, material_systems: [{ provider: 'bambu' }] } as PhysicalPrinter);
    expect(screen.queryByText('printerSetup.routes.edge')).not.toBeInTheDocument();
    savePrinter();
    await screen.findByText('printerSetup.saved');
    expect(mocks.setup).toHaveBeenCalledWith(7, expect.not.objectContaining({ material_system: expect.anything() }));
    expect(mocks.create).not.toHaveBeenCalled();
    expect(screen.queryByText('edge-setup')).not.toBeInTheDocument();
  });
  it('blocks a selected Edge route if refreshed data reveals an unsupported system', async () => {
    const { client } = show(saved);
    chooseMoonraker();
    fireEvent.click(screen.getByText('printerSetup.routes.edge'));
    await waitFor(() => expect(client.isFetching({ queryKey: ['physical-printers'] })).toBe(0));
    await act(async () => {
      client.setQueryData(['physical-printers'], [{ ...saved, material_systems: [{ provider: 'octoprint' }] }]);
    });
    expect(screen.getByText('printerSetup.routes.edge')).toHaveAttribute('aria-pressed', 'true');
    await waitFor(() => expect(screen.getByText('printerSetup.routes.edge')).toBeDisabled());
    expect(screen.getByText('printerSetup.connect')).toBeDisabled();
    fireEvent.submit(screen.getByText('printerSetup.connect').closest('form')!);
    expect(mocks.setup).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('printerSetup.routes.manual'));
    expect(screen.getByText('printerSetup.connect')).not.toBeDisabled();
  });
  it('allows correcting a rejected request without reusing its frozen payload', async () => {
    mocks.create.mockRejectedValueOnce({ response: { status: 422 } });
    show(); await namePrinter(); savePrinter();
    await screen.findByRole('alert');
    expect(screen.queryByText('printerSetup.resume')).not.toBeInTheDocument();
    expect(screen.getByLabelText('printerSetup.name')).not.toBeDisabled();
  });
  it('attaches to the explicitly selected existing printer instead of creating a card', async () => {
    show(saved);
    savePrinter();
    await screen.findByText('printerSetup.saved');
    expect(mocks.setup).toHaveBeenCalledWith(7, expect.any(Object));
    expect(mocks.create).not.toHaveBeenCalled();
  });
  it('offers manual fallback immediately when local plugin capabilities are unavailable', async () => {
    show(); await namePrinter();
    chooseMoonraker();
    fireEvent.click(screen.getByText('printerSetup.routes.orca'));
    expect(screen.getByText('printerSetup.pluginUnavailable')).toBeInTheDocument();
    expect(screen.getByText('printerSetup.save')).toBeDisabled();
    fireEvent.click(screen.getByText('printerSetup.routes.manual'));
    expect(screen.getByText('printerSetup.save')).not.toBeDisabled();
  });
  it('retries activation, not printer creation, after a failed first snapshot', async () => {
    mocks.embed = true;
    mocks.plugin.mockImplementation(async (op: string) => op === 'list'
      ? { ok: true, candidates: [{ label: 'Local Voron', connectionRef: 'ref-1' }] }
      : op === 'probe' ? probe : { ok: false });
    show(); await namePrinter(); chooseMoonraker(); fireEvent.click(screen.getByText('printerSetup.routes.orca'));
    fireEvent.click(await screen.findByText('Local Voron'));
    await screen.findByText('printerSetup.probeGates');
    fireEvent.click(screen.getByText('printerSetup.save'));
    await screen.findByText('printerSetup.savedConnectionFailed');
    mocks.plugin.mockResolvedValue({ ok: true, observed: true });
    fireEvent.click(screen.getByText('printerSetup.retryConnection'));
    await screen.findByText('printerSetup.observed');
    expect(mocks.create).toHaveBeenCalledTimes(1);
    expect(mocks.plugin).toHaveBeenLastCalledWith('activate', { probeId: 'probe-1', physicalPrinterId: 7 });
  });
  it('rejects a local connection already belonging to another selected card', async () => {
    mocks.embed = true;
    mocks.plugin.mockResolvedValue({ ok: true, candidates: [{ label: 'Other', connectionRef: 'ref-2', physicalPrinterId: 9 }] });
    show(saved); chooseMoonraker(); fireEvent.click(screen.getByText('printerSetup.routes.orca'));
    fireEvent.click(await screen.findByText('Other · #9'));
    await waitFor(() => expect(screen.getByText('printerSetup.otherCard')).toBeInTheDocument());
    expect(mocks.plugin).toHaveBeenCalledTimes(1); expect(mocks.setup).not.toHaveBeenCalled();
  });
  it('selects an already added printer without presenting its Orca connection as another printer', async () => {
    mocks.embed = true;
    mocks.printers.mockResolvedValue([saved]);
    mocks.plugin.mockResolvedValue({ ok: true, candidates: [{ label: 'Same Workshop connection', connectionRef: 'ref-1', physicalPrinterId: 7 }] });
    show();
    const existing = await screen.findByRole('button', { name: /Workshop —/ });
    await waitFor(() => expect(existing).not.toBeDisabled());
    expect(screen.queryByText('Same Workshop connection')).not.toBeInTheDocument();
    fireEvent.click(existing); savePrinter();
    await screen.findByText('printerSetup.saved');
    expect(mocks.setup).toHaveBeenCalledWith(7, expect.any(Object));
    expect(mocks.create).not.toHaveBeenCalled();
  });
  it('offers a new Orca connection before any integration choice and retains its target after a failed probe', async () => {
    mocks.embed = true;
    mocks.plugin.mockImplementation(async (op: string) => op === 'list'
      ? { ok: true, candidates: [{ label: 'Workshop connection', connectionRef: 'ref-1', physicalPrinterId: 7 }] }
      : { ok: false, code: 'unreachable' });
    show();
    expect(screen.queryByText('printerSetup.routes.orca')).not.toBeInTheDocument();
    fireEvent.click(await screen.findByText('Workshop connection'));
    await screen.findByRole('alert');
    expect(screen.getByText('printerSetup.connect')).toBeDisabled();
    fireEvent.click(screen.getByText('printerSetup.routes.manual')); savePrinter();
    await screen.findByText('printerSetup.saved');
    expect(mocks.setup).toHaveBeenCalledWith(7, expect.any(Object));
    expect(mocks.create).not.toHaveBeenCalled();
  });
  it('does not create on selection and clears an existing target when going back to manual addition', async () => {
    mocks.printers.mockResolvedValue([saved]);
    show();
    fireEvent.click(await screen.findByRole('button', { name: /Workshop —/ }));
    expect(mocks.setup).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('printerSetup.back'));
    fireEvent.submit(screen.getByText('printerSetup.newDevice').closest('form')!);
    expect(mocks.create).not.toHaveBeenCalled();
    await namePrinter(); savePrinter();
    await screen.findByText('printerSetup.saved');
    expect(mocks.create).toHaveBeenCalledTimes(1); expect(mocks.setup).not.toHaveBeenCalled();
  });
  it('uses a catalog model as details for a manual printer, not as a detected connection', async () => {
    mocks.models.mockResolvedValue({ items: [{ id: 10, name: 'Voron 2.4' }] });
    show();
    expect(mocks.models).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('printerSetup.newDevice'));
    await waitFor(() => expect(mocks.models).toHaveBeenCalled());
    fireEvent.focus(screen.getByPlaceholderText('addPrinter.modelPlaceholder'));
    fireEvent.click(await screen.findByRole('button', { name: 'Voron 2.4' }));
    expect(screen.getByLabelText('printerSetup.name')).toHaveValue('Voron 2.4');
    expect(mocks.create).not.toHaveBeenCalled();
    savePrinter(); await screen.findByText('printerSetup.saved');
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ printer_id: 10, name: 'Voron 2.4' }));
    expect(mocks.plugin).not.toHaveBeenCalled();
  });
  it('keeps manual addition available while Orca inventory is slow or fails', async () => {
    mocks.embed = true;
    let finishList!: (result: unknown) => void;
    mocks.plugin.mockReturnValue(new Promise((resolve) => { finishList = resolve; }));
    show();
    expect(screen.getByText('printerSetup.loadingConnections')).toBeInTheDocument();
    expect(screen.getByText('printerSetup.newDevice')).not.toBeDisabled();
    await namePrinter();
    await act(async () => { finishList({ ok: false, code: 'unreachable' }); });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    savePrinter(); await screen.findByText('printerSetup.saved');
    expect(mocks.create).toHaveBeenCalledTimes(1);
  });

  it('uses Bambu equipment choices without offering unrelated connections or requiring AMS', async () => {
    mocks.models.mockResolvedValue({ items: [{ id: 10, name: 'Bambu Lab P1S', manufacturer: 'Bambu Lab' }] });
    show(); fireEvent.click(screen.getByText('printerSetup.newDevice'));
    fireEvent.focus(screen.getByLabelText('printerSetup.model'));
    fireEvent.click(await screen.findByRole('button', { name: 'Bambu Lab P1S' }));
    fireEvent.click(screen.getByText('printerSetup.connectionOptional'));
    expect(screen.queryByText('printerSetup.routes.edge')).not.toBeInTheDocument();
    expect(screen.queryByText('printerSetup.connections.octoprint')).not.toBeInTheDocument();
    expect(screen.getByLabelText('printerSetup.feed.label')).toHaveValue('printerSetup.feed.noAms');
    savePrinter(); await screen.findByText('printerSetup.saved');
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ material_system: expect.objectContaining({
      provider: 'bambu', kind: 'direct_feed', slots: [{ provider_index: 255, kind: 'external' }],
    }) }));
    expect(mocks.plugin).not.toHaveBeenCalled();
    expect(screen.queryByTestId('adapter-setup')).not.toBeInTheDocument();
  });

  it('connects OctoPrint natively and keeps the feed layout independent of the connection', async () => {
    show(); await namePrinter();
    fireEvent.focus(screen.getByLabelText('printerSetup.connectionType'));
    fireEvent.click(screen.getByText('printerSetup.connections.octoprint'));
    expect(screen.getByText('printerSetup.routes.native')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByText('printerSetup.routes.orca')).not.toBeInTheDocument();
    expect(screen.queryByText('printerSetup.routes.edge')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('printerSetup.feed.configure'));
    fireEvent.focus(screen.getByLabelText('printerSetup.feed.label'));
    fireEvent.click(screen.getByText('printerSetup.feed.tools'));
    savePrinter(); await screen.findByText('printerSetup.saved');
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ material_system: expect.objectContaining({
      provider: 'octoprint', kind: 'multi_tool', slots: [
        { provider_index: 0, kind: 'tool' }, { provider_index: 1, kind: 'tool' },
      ],
    }) }));
    expect(mocks.plugin).not.toHaveBeenCalled();
  });

  it('creates manually declared Happy Hare gates and bypass without generating a key or requiring Edge', async () => {
    show(); await namePrinter();
    fireEvent.focus(screen.getByLabelText('printerSetup.connectionType'));
    fireEvent.click(screen.getByText('printerSetup.connections.happyHare'));
    fireEvent.click(screen.getByText('printerSetup.routes.manual'));
    fireEvent.change(screen.getByLabelText('printerSetup.feed.gateCount'), { target: { value: '8' } });
    fireEvent.click(screen.getByLabelText('printerSetup.feed.bypass'));
    savePrinter(); await screen.findByText('printerSetup.saved');
    const system = mocks.create.mock.calls[0][0].material_system;
    expect(system.slots).toHaveLength(9);
    expect(system.slots[8]).toEqual({ provider_index: 1023, kind: 'bypass' });
    expect(mocks.key).not.toHaveBeenCalled(); expect(mocks.plugin).not.toHaveBeenCalled();
  });

  it('keeps an unknown model usable without silently picking a connection or turning independent tools into an MMU', async () => {
    show(); await namePrinter();
    expect(screen.getByLabelText('printerSetup.connectionType')).toHaveValue('');
    expect(screen.queryByText('printerSetup.routes.edge')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('printerSetup.feed.configure'));
    fireEvent.focus(screen.getByLabelText('printerSetup.feed.label'));
    fireEvent.click(screen.getByText('printerSetup.feed.tools'));
    savePrinter(); await screen.findByText('printerSetup.saved');
    expect(mocks.create.mock.calls[0][0].material_system).toMatchObject({ provider: 'manual', kind: 'multi_tool' });
  });

  it('applies model-specific options when opened from a saved printer configuration outside the search page', async () => {
    mocks.model.mockResolvedValue({ id: 99, name: 'Bambu Lab X1C', manufacturer: 'Bambulab' });
    show(undefined, 99);
    await waitFor(() => expect(screen.getByLabelText('printerSetup.feed.label')).toHaveValue('printerSetup.feed.noAms'));
    fireEvent.click(screen.getByText('printerSetup.connectionOptional'));
    expect(screen.getByLabelText('printerSetup.connectionType')).toHaveValue('printerSetup.connections.bambu');
    expect(screen.queryByText('printerSetup.routes.edge')).not.toBeInTheDocument();
  });

  it('restores a zero-slot Happy Hare card manually instead of sending an empty map', async () => {
    show({ ...saved, material_systems: [{ id: 4, provider: 'happy_hare', kind: 'mmu', slots: [] }] } as unknown as PhysicalPrinter);
    fireEvent.click(screen.getByText('printerSetup.feed.edit'));
    expect(screen.getByLabelText('printerSetup.feed.gateCount')).not.toBeDisabled();
    fireEvent.change(screen.getByLabelText('printerSetup.feed.gateCount'), { target: { value: '8' } });
    savePrinter(); await screen.findByText('printerSetup.saved');
    const payload = mocks.setup.mock.calls[0][1];
    expect(payload.material_system).toBeUndefined();
    expect(payload.material_system_update.slots).toHaveLength(8);
    expect(payload.material_system_update.expected_slots).toEqual([]);
  });

  it('uses the known model when configuring an already imported printer without a feed system', async () => {
    mocks.model.mockResolvedValue({ id: 99, name: 'Bambu Lab P1S', manufacturer: 'Bambulab' });
    show({ ...saved, printer_id: 99 });
    await waitFor(() => expect(screen.getByLabelText('printerSetup.connectionType')).toHaveValue('printerSetup.connections.bambu'));
    expect(screen.queryByText('printerSetup.routes.edge')).not.toBeInTheDocument();
    expect(screen.getByLabelText('printerSetup.feed.label')).toHaveValue('printerSetup.feed.noAms');
    savePrinter(); await screen.findByText('printerSetup.saved');
    expect(mocks.setup.mock.calls[0][0]).toBe(saved.id);
    expect(mocks.setup.mock.calls[0][1].material_system.provider).toBe('bambu');
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it('preserves sparse provider indices, labels, and expectations when reopening or retrying a topology edit', async () => {
    const slots = [0, 128, 255].map((index) => ({ id: index + 10, provider_index: index,
      kind: index === 255 ? 'external' : 'slot', label: `Position ${index}`, active: true,
      assignment_revision: 3, assignment: null, legacy_projection: null }));
    const printer = { ...saved, material_systems: [{ id: 4, provider: 'bambu', kind: 'mmu', slots }] } as unknown as PhysicalPrinter;
    mocks.setup.mockRejectedValueOnce(new Error('response lost')).mockResolvedValueOnce(printer);
    const view = show(printer);
    fireEvent.click(screen.getByText('printerSetup.feed.edit'));
    expect(screen.getByLabelText('printerSetup.feed.amsSlots')).toBeDisabled();
    savePrinter(); await screen.findByRole('alert');
    const payload = mocks.setup.mock.calls[0][1];
    expect(payload.material_system_update.slots).toEqual(slots.map(({ provider_index, kind, label }) => ({ provider_index, kind, label })));
    expect(payload.material_system_update.expected_slots).toEqual(slots.map((slot) => ({ material_slot_id: slot.id, expected_spool_id: null, expected_revision: 3 })));
    view.unmount(); show(printer);
    fireEvent.click(screen.getByText('printerSetup.resumeButton'));
    await screen.findByText('printerSetup.saved');
    expect(mocks.setup.mock.calls[1][1]).toEqual(payload);
    expect(mocks.create).not.toHaveBeenCalled();
  });
});
