import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PrinterSetupWizard } from '../components/PrinterSetupWizard';
import type { PhysicalPrinter } from '../api/client';

const mocks = vi.hoisted(() => ({
  create: vi.fn(), setup: vi.fn(), plugin: vi.fn(), key: vi.fn(), embed: false,
  printers: vi.fn(), models: vi.fn(), installed: vi.fn(),
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 1 } }) }));
vi.mock('../api/client', () => ({
  physicalPrintersAPI: { create: mocks.create, setupConnection: mocks.setup,
    list: mocks.printers, listInstalledCandidates: mocks.installed, listBindings: async () => [] },
  printersAPI: { list: mocks.models }, devicesAPI: { regenerateKey: mocks.key },
}));
vi.mock('../utils/pluginBridge', () => ({
  isPluginEmbed: () => mocks.embed, requestPrinterSetup: mocks.plugin,
  requestPluginCapabilities: vi.fn(),
  subscribeToPluginCapabilities: (cb: (caps: Set<string>) => void) => {
    cb(new Set(['printer-setup-v1'])); return () => {};
  },
}));
vi.mock('../components/presetSlots/adapters', () => {
  const adapters = [{ id: 'manual', labelKey: 'direct', fixedSlots: 1, capabilities: [], link: null },
    { id: 'happy_hare', labelKey: 'happy_hare', topologyFromProvider: true, capabilities: ['read'], link: null }];
  return { FEED_ADAPTERS: adapters, feedAdapterFor: (id: string) => adapters.find((a) => a.id === id) ?? adapters[0],
    supportsEdgeSetup: (id: string) => ['manual', 'legacy', 'happy_hare'].includes(id) };
});
vi.mock('../components/presetSlots/EdgeConnectionSetup', () => ({ EdgeConnectionSetup: () => <div>edge-setup</div> }));

const saved = { id: 7, name: 'Workshop', printer_profile_ids: [], material_systems: [], connectors: [] } as unknown as PhysicalPrinter;
const probe = { ok: true, probeId: 'probe-1', provider: 'happy_hare', gateCount: 4,
  connection: { source_instance_id: 'local-desktop-source', connection_ref: 'ref-1',
    origin: 'orca_profile', provider: 'moonraker', endpoint_token: 'a'.repeat(64) } };

function show(physicalPrinter?: PhysicalPrinter) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { client, ...render(<QueryClientProvider client={client}>
    <PrinterSetupWizard onClose={vi.fn()} physicalPrinter={physicalPrinter} />
  </QueryClientProvider>) };
}
async function namePrinter() {
  await waitFor(() => expect(screen.getByText('printerSetup.newDevice')).not.toBeDisabled());
  fireEvent.click(screen.getByText('printerSetup.newDevice'));
  fireEvent.change(screen.getByLabelText('printerSetup.name'), { target: { value: 'Workshop' } });
  fireEvent.click(screen.getByText('printerSetup.connectionOptional'));
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
  it('disables Edge for an unsupported existing feed system without blocking manual tracking', async () => {
    show({ ...saved, material_systems: [{ provider: 'bambu' }] } as PhysicalPrinter);
    expect(screen.getByText('printerSetup.routes.edge')).toBeDisabled();
    expect(screen.getByText('printerSetup.edgeUnsupported')).toBeInTheDocument();
    savePrinter();
    await screen.findByText('printerSetup.saved');
    expect(mocks.setup).toHaveBeenCalledWith(7, expect.not.objectContaining({ material_system: expect.anything() }));
    expect(mocks.create).not.toHaveBeenCalled();
    expect(screen.queryByText('edge-setup')).not.toBeInTheDocument();
  });
  it('blocks a selected Edge route if refreshed data reveals an unsupported system', async () => {
    const { client } = show(saved);
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
    show(); await namePrinter(); fireEvent.click(screen.getByText('printerSetup.routes.orca'));
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
    show(saved); fireEvent.click(screen.getByText('printerSetup.routes.orca'));
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
});
