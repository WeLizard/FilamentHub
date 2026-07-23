import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const updateMock = vi.fn();
const setConfigurationsMock = vi.fn();

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

const profiles = [
  { id: 10, name: 'Voron 04', printer_id: 1, printer_model: 'Voron 2.4 350', nozzle_diameters: [0.4] },
  { id: 11, name: 'Voron 06', printer_id: 1, printer_model: 'Voron 2.4 350', nozzle_diameters: [0.6] },
];

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    const key = queryKey[0];
    if (key === 'printers') return { data: { items: [{ id: 1, name: 'Voron 2.4 350' }] } };
    if (key === 'printer') return { data: { id: 1, name: 'Voron 2.4 350' } };
    if (key === 'printer-profiles') return { data: profiles };
    return { data: undefined };
  },
  useMutation: ({
    mutationFn,
    onSuccess,
    onError,
  }: {
    mutationFn: () => Promise<unknown>;
    onSuccess?: (result: unknown) => void;
    onError?: (e: unknown) => void;
  }) => ({
    mutate: async () => {
      try {
        const result = await mutationFn();
        onSuccess?.(result);
      } catch (e) {
        onError?.(e);
      }
    },
    isPending: false,
  }),
}));

vi.mock('../api/client', () => ({
  physicalPrintersAPI: { update: updateMock, setConfigurations: setConfigurationsMock },
  printerProfilesAPI: { list: vi.fn() },
  printersAPI: { list: vi.fn(), get: vi.fn() },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1 } }),
}));

const basePrinter = {
  id: 5,
  logical_id: 'abc',
  printer_id: 1,
  name: 'My Voron',
  printer_profile_ids: [10],
  material_systems: [],
  connectors: [],
  created_at: '',
  updated_at: '',
};

async function renderModal(overrides: Record<string, unknown> = {}) {
  const { PhysicalPrinterSettingsModal } = await import('../components/PhysicalPrinterSettingsModal');
  const onClose = vi.fn();
  render(
    <PhysicalPrinterSettingsModal
      isOpen
      printer={{ ...basePrinter, ...overrides } as never}
      binding={null}
      onClose={onClose}
    />,
  );
  return { onClose };
}

describe('PhysicalPrinterSettingsModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMock.mockResolvedValue({});
    setConfigurationsMock.mockResolvedValue({});
  });

  it('renders name and the linked configuration', async () => {
    await renderModal();
    expect(screen.getByDisplayValue('My Voron')).toBeTruthy();
    expect(screen.getByText(/Voron 2\.4 350 · 0\.4/)).toBeTruthy();
  });

  it('saves name and catalog model without touching configurations when unchanged', async () => {
    await renderModal();
    fireEvent.change(screen.getByDisplayValue('My Voron'), { target: { value: 'Big Red' } });
    fireEvent.click(screen.getByText('common.save'));

    await waitFor(() => expect(updateMock).toHaveBeenCalledWith(5, { name: 'Big Red', printer_id: 1 }));
    expect(setConfigurationsMock).not.toHaveBeenCalled();
  });

  it('detaches a configuration and persists the reduced set on save', async () => {
    await renderModal();
    fireEvent.click(screen.getByTitle('printerSettings.detach'));
    expect(screen.queryByText(/Voron 2\.4 350 · 0\.4/)).toBeNull();

    fireEvent.click(screen.getByText('common.save'));
    await waitFor(() => expect(setConfigurationsMock).toHaveBeenCalledWith(5, []));
  });

  it('attaches an available configuration and persists it on save', async () => {
    await renderModal();
    // Open the "attach" dropdown and pick the 0.6 configuration (id 11).
    fireEvent.focus(screen.getByPlaceholderText('printerSettings.attachConfiguration'));
    fireEvent.click(await screen.findByText(/Voron 2\.4 350 · 0\.6/));

    fireEvent.click(screen.getByText('common.save'));
    await waitFor(() =>
      expect(setConfigurationsMock).toHaveBeenCalledWith(5, [10, 11]),
    );
  });

  it('reports partial success when configurations fail after basics saved', async () => {
    setConfigurationsMock.mockRejectedValue(new Error('network'));
    const { onClose } = await renderModal();
    fireEvent.click(screen.getByTitle('printerSettings.detach')); // change configs
    fireEvent.click(screen.getByText('common.save'));

    await waitFor(() =>
      expect(screen.getByText('printerSettings.savePartialError')).toBeTruthy(),
    );
    expect(updateMock).toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('guards unsaved changes before closing', async () => {
    const { onClose } = await renderModal();
    fireEvent.change(screen.getByDisplayValue('My Voron'), { target: { value: 'Changed' } });
    fireEvent.click(screen.getByText('common.cancel'));

    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText('unsavedGuard.title')).toBeTruthy();

    fireEvent.click(screen.getByText('unsavedGuard.confirm'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('surfaces a save error and does not close', async () => {
    updateMock.mockRejectedValue({ response: { data: { detail: undefined } } });
    const { onClose } = await renderModal();
    fireEvent.click(screen.getByText('common.save'));

    await waitFor(() => expect(screen.getByText('printerSettings.saveError')).toBeTruthy());
    expect(onClose).not.toHaveBeenCalled();
  });
});
