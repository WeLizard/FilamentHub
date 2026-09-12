import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MyPrintersList } from './MyPrintersList';

vi.mock('../hooks/usePrinterContactEvents', () => ({ usePrinterContactEvents: vi.fn() }));

const mocks = vi.hoisted(() => ({
  downloadBundle: vi.fn(),
  downloadBlob: vi.fn(),
  isPluginEmbed: vi.fn(),
  requestCapabilities: vi.fn(),
  listPrinters: vi.fn(),
  getPrinter: vi.fn(),
  pendingConnections: vi.fn(),
  getPrinterProfile: vi.fn(),
  listPrintProfiles: vi.fn(),
  capabilityListener: null as ((capabilities: ReadonlySet<string>) => void) | null,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: { count?: number }) =>
      values?.count == null ? key : `${key}:${values.count}`,
    i18n: { language: 'en' },
  }),
}));

vi.mock('../api/client', () => ({
  physicalPrintersAPI: {
    feed: (...args: unknown[]) => mocks.listPrinters(...args),
    get: (...args: unknown[]) => mocks.getPrinter(...args),
    listBindings: vi.fn().mockResolvedValue([]),
    pendingConnections: (...args: unknown[]) => mocks.pendingConnections(...args),
    downloadOrcaBundle: (...args: unknown[]) => mocks.downloadBundle(...args),
  },
  printerProfilesAPI: {
    get: (...args: unknown[]) => mocks.getPrinterProfile(...args),
  },
  printProfilesAPI: {
    listAllForConfigurations: (...args: unknown[]) => mocks.listPrintProfiles(...args),
  },
}));

vi.mock('../utils/pluginBridge', () => ({
  isPluginEmbed: () => mocks.isPluginEmbed(),
  requestPluginCapabilities: () => mocks.requestCapabilities(),
  subscribeToPluginCapabilities: (
    listener: (capabilities: ReadonlySet<string>) => void,
  ) => {
    mocks.capabilityListener = listener;
    return vi.fn();
  },
}));

vi.mock('../utils/download', () => ({
  downloadBlob: (...args: unknown[]) => mocks.downloadBlob(...args),
  safeDownloadStem: (value: string) => value,
}));

vi.mock('./Toast', () => ({
  toast: { info: vi.fn(), success: vi.fn(), error: vi.fn() },
}));

vi.mock('./AddPhysicalPrinterModal', () => ({ AddPhysicalPrinterModal: () => null }));
vi.mock('./PhysicalPrinterSettingsModal', () => ({ PhysicalPrinterSettingsModal: () => null }));
vi.mock('./PrinterRecoveryModal', () => ({
  PrinterRecoveryModal: ({ ownerUserId }: { ownerUserId: number }) => (
    <div>recovery-modal:{ownerUserId}</div>
  ),
}));
vi.mock('./PrinterConfigurationRow', () => ({
  PrinterConfigurationRow: ({ profile }: { profile: { name: string } }) => (
    <span data-testid="printer-configuration">{profile.name}</span>
  ),
}));

function renderList(
  printerProfiles = [
    { id: 11, name: 'Config One', owner_user_id: 7 },
    { id: 22, name: 'Config Two', owner_user_id: 7 },
  ],
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MyPrintersList
        printerProfiles={printerProfiles as never}
        currentUserId={7}
      />
    </QueryClientProvider>,
  );
}

const feedPage = (
  items: Array<Record<string, unknown>>,
  nextCursor: string | null = null,
) => ({
  items,
  next_cursor: nextCursor,
  has_more: nextCursor !== null,
  total: items.length,
});

describe('MyPrintersList Orca bundle action', () => {
  it('passes a cancellable signal to the printer list and aborts on unmount', async () => {
    mocks.listPrinters.mockImplementation(() => new Promise(() => {}));
    const view = renderList();
    try {
      await waitFor(() => expect(mocks.listPrinters).toHaveBeenCalled());
      const signal = mocks.listPrinters.mock.calls[0][1];
      expect(signal).toBeInstanceOf(AbortSignal);
      view.unmount();
      expect(signal.aborted).toBe(true);
    } finally {
      view.unmount();
    }
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.capabilityListener = null;
    mocks.downloadBundle.mockResolvedValue(new Blob(['bundle']));
    mocks.listPrintProfiles.mockResolvedValue([]);
    mocks.getPrinter.mockReset();
    mocks.pendingConnections.mockReset();
    mocks.pendingConnections.mockResolvedValue([]);
    mocks.listPrinters.mockResolvedValue(feedPage([
      {
        id: 1,
        name: 'Printer One',
        printer_profile_ids: [11],
        material_systems: [],
      },
      {
        id: 2,
        name: 'Printer Two',
        printer_profile_ids: [22],
        material_systems: [],
      },
    ]));
  });

  it('shows one explicit Recovery Center only after the plugin advertises it', async () => {
    mocks.isPluginEmbed.mockReturnValue(true);
    renderList();

    await screen.findByText('Printer One');
    expect(screen.queryByRole('button', { name: 'printerRecovery.open' })).toBeNull();
    expect(mocks.requestCapabilities).toHaveBeenCalledOnce();

    act(() => {
      mocks.capabilityListener?.(new Set(['printer-recovery-v1']));
    });

    const action = screen.getByRole('button', { name: 'printerRecovery.open' });
    expect(screen.queryByRole('button', { name: 'myPrinters.installBundleInOrca' })).toBeNull();
    fireEvent.click(action);
    expect(screen.getByText('recovery-modal:7')).toBeInTheDocument();
    expect(mocks.downloadBundle).not.toHaveBeenCalled();
  });

  it('does not fetch any per-printer bundle merely by opening the list', async () => {
    mocks.isPluginEmbed.mockReturnValue(true);
    renderList();
    await screen.findByText('Printer One');
    act(() => {
      mocks.capabilityListener?.(new Set(['printer-recovery-v1']));
    });
    expect(screen.getByRole('button', { name: 'printerRecovery.open' })).toBeEnabled();
    expect(mocks.downloadBundle).not.toHaveBeenCalled();
  });

  it('never shows the old circular install/remove controls in the embed', async () => {
    mocks.isPluginEmbed.mockReturnValue(true);
    renderList();
    await screen.findByText('Printer One');

    act(() => {
      mocks.capabilityListener?.(new Set(['printer-recovery-v1']));
    });

    expect(screen.queryByRole('button', { name: 'myPrinters.installBundleInOrca' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'myPrinters.removeBundleFromOrca' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'myPrinters.downloadBundle' })).toBeNull();
  });

  it('keeps install actions hidden in an embed without the capability', async () => {
    mocks.isPluginEmbed.mockReturnValue(true);
    renderList();
    await screen.findByText('Printer One');

    act(() => {
      mocks.capabilityListener?.(new Set());
    });

    expect(screen.queryByRole('button', { name: 'myPrinters.installBundleInOrca' })).toBeNull();
  });

  it('keeps archive downloads available on the ordinary website', async () => {
    mocks.isPluginEmbed.mockReturnValue(false);
    renderList();

    const actions = await screen.findAllByRole('button', {
      name: 'myPrinters.downloadBundle',
    });
    fireEvent.click(actions[0]);

    await waitFor(() => expect(mocks.downloadBundle).toHaveBeenCalledWith(1));
  });

  it('marks only the selected printer while its archive is being prepared', async () => {
    mocks.isPluginEmbed.mockReturnValue(false);
    let resolveDownload: ((bundle: Blob) => void) | undefined;
    mocks.downloadBundle.mockReturnValue(
      new Promise<Blob>((resolve) => {
        resolveDownload = resolve;
      }),
    );
    renderList();

    const actions = await screen.findAllByRole('button', {
      name: 'myPrinters.downloadBundle',
    });
    fireEvent.click(actions[0]);

    await waitFor(() => expect((actions[0] as HTMLButtonElement).disabled).toBe(true));
    expect((actions[1] as HTMLButtonElement).disabled).toBe(false);

    act(() => resolveDownload?.(new Blob(['bundle'])));
    await waitFor(() => expect((actions[0] as HTMLButtonElement).disabled).toBe(false));
  });

  it('loads an official configuration linked to a physical printer by id', async () => {
    mocks.isPluginEmbed.mockReturnValue(false);
    mocks.listPrinters.mockResolvedValue(feedPage([
      {
        id: 3,
        name: 'Printer with official configuration',
        printer_profile_ids: [33],
        material_systems: [],
      },
    ]));
    mocks.getPrinterProfile.mockResolvedValue({
      id: 33,
      name: 'Official machine configuration',
      is_official: true,
      owner_user_id: null,
    });

    renderList();

    await waitFor(() => expect(mocks.getPrinterProfile).toHaveBeenCalledWith(
      33,
      expect.any(AbortSignal),
    ));
    fireEvent.click(screen.getByRole('button', { name: /profilePage\.profilesCount:1/ }));
    expect(await screen.findByText('Official machine configuration')).toBeInTheDocument();
    expect(mocks.getPrinterProfile).toHaveBeenCalledWith(33, expect.any(AbortSignal));
  });

  it('keeps configurations compact, then orders and progressively reveals them', async () => {
    mocks.isPluginEmbed.mockReturnValue(false);
    mocks.listPrinters.mockResolvedValue(feedPage([
      {
        id: 7,
        name: 'Voron 2.4 350',
        printer_profile_ids: [11, 12, 13, 14, 15, 16],
        material_systems: [],
      },
    ]));
    const profiles = [
      { id: 11, name: 'Nozzle 0.8', nozzle_diameters: [0.8], owner_user_id: 7 },
      { id: 12, name: 'Nozzle 0.15', nozzle_diameters: [0.15], owner_user_id: 7 },
      { id: 13, name: 'Nozzle 0.6', nozzle_diameters: [0.6], owner_user_id: 7 },
      { id: 14, name: 'Nozzle 0.25', nozzle_diameters: [0.25], owner_user_id: 7 },
      { id: 15, name: 'Nozzle 0.4', nozzle_diameters: [0.4], owner_user_id: 7 },
      { id: 16, name: 'Nozzle 1.0', nozzle_diameters: [1.0], owner_user_id: 7 },
    ];

    renderList(profiles);

    await screen.findByText('Voron 2.4 350');
    expect(screen.queryAllByTestId('printer-configuration')).toHaveLength(0);
    const configurationSection = screen.getByRole('button', {
      name: /profilePage\.profilesCount:6/,
    });
    expect(configurationSection).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('myPrinters.configurations')).not.toBeInTheDocument();

    fireEvent.click(configurationSection);

    expect(configurationSection).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getAllByTestId('printer-configuration').map((row) => row.textContent)).toEqual([
      'Nozzle 0.15',
      'Nozzle 0.25',
      'Nozzle 0.4',
      'Nozzle 0.6',
    ]);
    fireEvent.click(
      screen.getByRole('button', {
        name: 'filamentDetailPage.showMorePresets +2',
      }),
    );

    expect(screen.getAllByTestId('printer-configuration').map((row) => row.textContent)).toEqual([
      'Nozzle 0.15',
      'Nozzle 0.25',
      'Nozzle 0.4',
      'Nozzle 0.6',
      'Nozzle 0.8',
      'Nozzle 1.0',
    ]);
    expect(
      screen.getByRole('button', { name: 'profilePage.hideDetails' }),
    ).toHaveAttribute('aria-expanded', 'true');
  });

  it('loads a second page and stops at the terminal page', async () => {
    mocks.isPluginEmbed.mockReturnValue(false);
    mocks.listPrinters
      .mockResolvedValueOnce(feedPage([{
        id: 41, name: 'Page one', printer_profile_ids: [], material_systems: [], connectors: [],
      }], 'next-page'))
      .mockResolvedValueOnce(feedPage([{
        id: 42, name: 'Page two', printer_profile_ids: [], material_systems: [], connectors: [],
      }]));
    renderList();

    fireEvent.click(await screen.findByRole('button', { name: 'myPrinters.loadMore' }));
    expect(await screen.findByText('Page two')).toBeInTheDocument();
    expect(screen.getByText('Page one')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'myPrinters.loadMore' })).toBeNull();
    expect(mocks.listPrinters).toHaveBeenLastCalledWith(
      { cursor: 'next-page', size: 12 },
      expect.any(AbortSignal),
    );
  });

  it('retries an initial error without hiding the rest of the printer screen', async () => {
    mocks.isPluginEmbed.mockReturnValue(false);
    mocks.listPrinters
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(feedPage([{
        id: 51, name: 'Recovered printer', printer_profile_ids: [], material_systems: [], connectors: [],
      }]));
    renderList();

    fireEvent.click(await screen.findByRole('button', { name: 'myPrinters.retry' }));
    expect(await screen.findByText('Recovered printer')).toBeInTheDocument();
    expect(mocks.listPrinters).toHaveBeenCalledTimes(2);
  });

  it('keeps page one and a retryable load-more action after page two fails', async () => {
    mocks.isPluginEmbed.mockReturnValue(false);
    mocks.listPrinters
      .mockResolvedValueOnce(feedPage([{
        id: 61, name: 'Still visible', printer_profile_ids: [], material_systems: [], connectors: [],
      }], 'next-page'))
      .mockRejectedValueOnce(new Error('page two failed'))
      .mockResolvedValueOnce(feedPage([{
        id: 62, name: 'Recovered page two', printer_profile_ids: [], material_systems: [], connectors: [],
      }]));
    renderList();

    fireEvent.click(await screen.findByRole('button', { name: 'myPrinters.loadMore' }));
    expect(await screen.findByText('myPrinters.loadMoreError')).toBeInTheDocument();
    expect(screen.getByText('Still visible')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'myPrinters.loadMore' }));
    expect(await screen.findByText('Recovered page two')).toBeInTheDocument();
    expect(screen.queryByText('myPrinters.loadMoreError')).toBeNull();
    expect(screen.queryByRole('button', { name: 'myPrinters.loadMore' })).toBeNull();
  });

  it('loads exact owned details for pending candidates outside the visible page', async () => {
    mocks.isPluginEmbed.mockReturnValue(false);
    mocks.pendingConnections.mockResolvedValueOnce([{
      id: 71,
      revision: 'r1',
      preset_name: 'Observed machine',
      provider: 'orca',
      candidate_printer_ids: [72],
      last_seen_at: '2026-09-12T12:00:00Z',
    }]);
    mocks.getPrinter.mockResolvedValueOnce({
      id: 72,
      name: 'Candidate on later page',
      printer_profile_ids: [],
      material_systems: [],
      connectors: [],
    });
    renderList();

    await waitFor(() => expect(mocks.getPrinter).toHaveBeenCalledWith(72, expect.any(AbortSignal)));
    fireEvent.focus(screen.getByPlaceholderText('printerConnections.choose'));
    expect(await screen.findByText('Candidate on later page · #72')).toBeInTheDocument();
  });
});
