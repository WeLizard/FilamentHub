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
  capabilityListener: null as ((capabilities: ReadonlySet<string>) => void) | null,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../api/client', () => ({
  physicalPrintersAPI: {
    list: vi.fn().mockResolvedValue([
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
    ]),
    listBindings: vi.fn().mockResolvedValue([]),
    downloadOrcaBundle: (...args: unknown[]) => mocks.downloadBundle(...args),
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
  PrinterConfigurationRow: ({ profile }: { profile: { name: string } }) => <span>{profile.name}</span>,
}));

function renderList() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MyPrintersList
        printerProfiles={[
          { id: 11, name: 'Config One' },
          { id: 22, name: 'Config Two' },
        ] as never}
      />
    </QueryClientProvider>,
  );
}

describe('MyPrintersList Orca bundle action', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.capabilityListener = null;
    mocks.downloadBundle.mockResolvedValue(new Blob(['bundle']));
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

    fireEvent.click(actions[0]);
    expect(mocks.installBundle).toHaveBeenCalledWith(1);
    expect(mocks.downloadBundle).not.toHaveBeenCalled();
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
});
