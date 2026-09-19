import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AdminMaterials } from './AdminMaterials';

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../../api/client', () => ({
  filamentsAPI: {
    list: (...args: unknown[]) => mocks.list(...args),
    update: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../CreateFilamentModal', () => ({
  CreateFilamentModal: ({ onClose }: { onClose: () => void }) => (
    <button type="button" onClick={onClose}>finish edit</button>
  ),
}));

vi.mock('../FilamentPreview', () => ({
  FilamentPreview: () => <div />,
}));

vi.mock('../ConfirmDeleteModal', () => ({
  ConfirmDeleteModal: () => null,
}));

vi.mock('../Toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const material = (name: string) => ({
  id: 42,
  name,
  material_type: 'PETG',
  brand_name: 'Test Brand',
  color_name: null,
  color_hex: '#FFFFFF',
  visual_settings: null,
  active: true,
  presets_count: 0,
});

describe('AdminMaterials catalogue refresh', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.list
      .mockResolvedValueOnce({ items: [material('PETG')], total: 1, pages: 1 })
      .mockResolvedValueOnce({ items: [material('PETG')], total: 1, pages: 1 })
      .mockResolvedValue({ items: [material('PETG1')], total: 1, pages: 1 });
  });

  it('bypasses the shared catalogue cache and refreshes the active search after editing', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <AdminMaterials />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('heading', { name: 'PETG' })).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('adminMaterials.searchPlaceholder'), {
      target: { value: 'petg' },
    });
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith({
      page: 1,
      size: 20,
      active_only: false,
      search: 'petg',
    }, { bypassSharedCache: true }));

    fireEvent.click(screen.getByRole('button', { name: 'adminMaterials.edit' }));
    fireEvent.click(await screen.findByRole('button', { name: 'finish edit' }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'PETG1' })).toBeInTheDocument());
    expect(mocks.list).toHaveBeenCalledTimes(3);
  });
});
