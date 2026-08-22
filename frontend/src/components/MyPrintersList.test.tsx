import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MyPrintersList } from './MyPrintersList';

const mocks = vi.hoisted(() => ({
  downloadBundle: vi.fn(),
  downloadBlob: vi.fn(),
  installBundle: vi.fn(),
  isPluginEmbed: vi.fn(),
  requestCapabilities: vi.fn(),
  listPrinters: vi.fn(),
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
    list: (...args: unknown[]) => mocks.listPrinters(...args),
    listBindings: vi.fn().mockResolvedValue([]),
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
  installPrinterBundleInPlugin: (...args: unknown[]) => mocks.installBundle(...args),
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
vi.mock('./PrinterConfigurationRow', () => ({
  PrinterConfigurationRow: ({ profile }: { profile: { name: string } }) => (
    <span data-testid="printer-configuration">{profile.name}</span>
  ),
}));

function renderList(
  printerProfiles = [
    { id: 11, name: 'Config One' },
    { id: 22, name: 'Config Two' },
  ],
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MyPrintersList
        printerProfiles={printerProfiles as never}
      />
    </QueryClientProvider>,
  );
}

describe('MyPrintersList Orca bundle action', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.capabilityListener = null;
    mocks.downloadBundle.mockResolvedValue(new Blob(['bundle']));
    mocks.installBundle.mockResolvedValue({ message: 'installed' });
    mocks.listPrintProfiles.mockResolvedValue([]);
    mocks.listPrinters.mockResolvedValue([
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
    ]);
  });

  it('shows install actions only after a supporting plugin advertises the capability', async () => {
    mocks.isPluginEmbed.mockReturnValue(true);
    renderList();

    await screen.findByText('Printer One');
    expect(screen.queryByRole('button', { name: 'myPrinters.installBundleInOrca' })).toBeNull();
    expect(mocks.requestCapabilities).toHaveBeenCalledOnce();

    act(() => {
      mocks.capabilityListener?.(new Set(['printer-bundle-install']));
    });

    const actions = screen.getAllByRole('button', {
      name: 'myPrinters.installBundleInOrca',
    });
    expect(actions).toHaveLength(2);

    await act(async () => {
      fireEvent.click(actions[0]);
      await Promise.resolve();
    });
    expect(mocks.installBundle).toHaveBeenCalledWith(1);
    expect(mocks.downloadBundle).not.toHaveBeenCalled();
  });

  it('keeps only the matching printer busy until the plugin confirms installation', async () => {
    mocks.isPluginEmbed.mockReturnValue(true);
    let resolveInstall: ((result: { message: string }) => void) | undefined;
    mocks.installBundle.mockReturnValue(new Promise((resolve) => {
      resolveInstall = resolve;
    }));
    renderList();
    await screen.findByText('Printer One');
    act(() => {
      mocks.capabilityListener?.(new Set(['printer-bundle-install']));
    });
    const actions = screen.getAllByRole('button', {
      name: 'myPrinters.installBundleInOrca',
    });

    fireEvent.click(actions[0]);
    await waitFor(() => expect(actions[0]).toBeDisabled());
    expect(actions[1]).toBeEnabled();

    act(() => resolveInstall?.({ message: 'installed' }));
    await waitFor(() => expect(actions[0]).toBeEnabled());
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
    expect(mocks.installBundle).not.toHaveBeenCalled();
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
    mocks.listPrinters.mockResolvedValue([
      {
        id: 3,
        name: 'Printer with official configuration',
        printer_profile_ids: [33],
        material_systems: [],
      },
    ]);
    mocks.getPrinterProfile.mockResolvedValue({
      id: 33,
      name: 'Official machine configuration',
      is_official: true,
      owner_user_id: null,
    });

    renderList();

    expect(await screen.findByText('Official machine configuration')).toBeInTheDocument();
    expect(mocks.getPrinterProfile).toHaveBeenCalledWith(33);
  });

  it('orders configurations by nozzle and collapses a long list without hiding it permanently', async () => {
    mocks.isPluginEmbed.mockReturnValue(false);
    mocks.listPrinters.mockResolvedValue([
      {
        id: 7,
        name: 'Voron 2.4 350',
        printer_profile_ids: [11, 12, 13, 14, 15, 16],
        material_systems: [],
      },
    ]);
    const profiles = [
      { id: 11, name: 'Nozzle 0.8', nozzle_diameters: [0.8] },
      { id: 12, name: 'Nozzle 0.15', nozzle_diameters: [0.15] },
      { id: 13, name: 'Nozzle 0.6', nozzle_diameters: [0.6] },
      { id: 14, name: 'Nozzle 0.25', nozzle_diameters: [0.25] },
      { id: 15, name: 'Nozzle 0.4', nozzle_diameters: [0.4] },
      { id: 16, name: 'Nozzle 1.0', nozzle_diameters: [1.0] },
    ];

    renderList(profiles);

    await screen.findByText('Voron 2.4 350');
    expect(screen.getAllByTestId('printer-configuration').map((row) => row.textContent)).toEqual([
      'Nozzle 0.15',
      'Nozzle 0.25',
      'Nozzle 0.4',
      'Nozzle 0.6',
    ]);
    expect(
      screen.getByText(
        (content, element) =>
          element?.tagName === 'P' && content.includes('profilePage.profilesCount:6'),
      ),
    ).toBeInTheDocument();

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
});
