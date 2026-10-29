import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SpoolCollection, SpoolFeedResponse, SpoolGroupsResponse, UserSpool } from '../api/client';

const api = vi.hoisted(() => ({
  feed: vi.fn(),
  groups: vi.fn(),
  listCollections: vi.fn(),
  createCollection: vi.fn(),
  deleteCollection: vi.fn(),
  updateCollectionMembers: vi.fn(),
}));

vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));
vi.mock('../contexts/AuthContext', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../contexts/AuthContext')>()),
  useAuth: () => ({ user: { id: 1 } }),
}));
vi.mock('../hooks/useUserCurrency', () => ({ useUserCurrency: () => ({ currency: 'RUB' }) }));
vi.mock('../components/SpoolLabelButton', () => ({ SpoolLabelButton: () => null }));
vi.mock('../components/SpoolTagsButton', () => ({ SpoolTagsButton: () => null }));
vi.mock('../components/SpoolUsageModal', () => ({ SpoolUsageModal: () => null }));
vi.mock('../components/SpoolManagerImportButton', () => ({ SpoolImportButton: () => null }));
vi.mock('../components/Toast', () => ({
  toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));
vi.mock('../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/client')>();
  return { ...original, spoolsAPI: { ...original.spoolsAPI, ...api } };
});

import { SpoolsTab } from './ProfilePage';

const spool = (id: number, collection_ids: number[] = []): UserSpool => ({
  id, user_id: 1, filament_id: 12,
  filament: { id: 12, name: 'Galaxy PLA', material_type: 'PLA', color_name: null, color_hex: '3366ff',
    brand_name: 'Acme', price_per_kg: null, currency: null, required_nozzle_hrc: null },
  initial_weight_g: 1000, used_weight_g: 200, remaining_weight_g: 800, remaining_pct: 80,
  price: null, currency: null, state: 'active', source: 'manual', lot_nr: null, comment: null,
  created_at: '2026-10-20T00:00:00Z', updated_at: '2026-10-20T00:00:00Z', last_used_at: null,
  extra: null, collection_ids,
});

const feedPage = (items: UserSpool[]): SpoolFeedResponse => ({
  items,
  next_cursor: null,
  summary: { total: items.length, state_counts: { active: items.length, shelf: 0, archived: 0, empty: 0 }, available_remaining_weight_g: null },
});

let folders: SpoolCollection[] = [];

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SpoolsTab
        spools={[]}
        printerProfiles={[]}
        onRefetch={vi.fn()}
        showNewcomerGuide={false}
        isAddOpen={false}
        setIsAddOpen={vi.fn()}
        onResolveImport={vi.fn()}
        onResolveCompatImport={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

describe('Spool shelf grouping and folders', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    folders = [];
    api.listCollections.mockImplementation(async () => folders);
    api.feed.mockImplementation(async (params: { group_key?: string }) => (
      params.group_key ? feedPage([spool(1), spool(2)]) : feedPage([spool(1), spool(2), spool(3)])
    ));
  });

  it('groups the tab by material and loads a group only when it is expanded', async () => {
    const groups: SpoolGroupsResponse = {
      items: [
        { key: 'f:12', spool_count: 2, state_counts: { active: 2, shelf: 0, archived: 0, empty: 0 },
          available_remaining_weight_g: 1600, unknown_mass_count: 1, latest_spool: spool(1) },
        { key: 's:3', spool_count: 1, state_counts: { active: 1, shelf: 0, archived: 0, empty: 0 },
          available_remaining_weight_g: 800, unknown_mass_count: 0, latest_spool: spool(3) },
      ],
      next_cursor: null,
      summary: { total: 3, group_count: 2, available_remaining_weight_g: 2400, unknown_mass_count: 1 },
    };
    api.groups.mockResolvedValue(groups);
    renderTab();
    await screen.findAllByText('Galaxy PLA');

    fireEvent.click(screen.getByRole('button', { name: /profilePage.spoolShelf.groupToggle/ }));
    const header = (await screen.findByText('profilePage.spoolShelf.spoolCount')).closest('button')!;
    expect(api.groups).toHaveBeenCalledWith(expect.objectContaining({ state: 'active', limit: 24 }), expect.anything());
    expect(within(header).getByText('profilePage.spoolShelf.unknownMass')).toBeInTheDocument();
    expect(api.feed).not.toHaveBeenCalledWith(expect.objectContaining({ group_key: 'f:12' }), expect.anything());

    fireEvent.click(header);
    await waitFor(() => expect(api.feed).toHaveBeenCalledWith(
      expect.objectContaining({ group_key: 'f:12', state: 'active' }),
      expect.anything(),
    ));
    expect(header).toHaveAttribute('aria-expanded', 'true');
  });

  it('creates a folder and puts a spool into it', async () => {
    api.createCollection.mockImplementation(async (name: string) => {
      folders = [{ id: 5, name, spool_count: 0 }];
      return folders[0];
    });
    api.updateCollectionMembers.mockResolvedValue({ id: 5, name: 'Dry box', spool_count: 1 });
    renderTab();
    await screen.findAllByText('Galaxy PLA');

    fireEvent.click(screen.getByRole('button', { name: 'profilePage.spoolShelf.newFolder' }));
    const input = screen.getByRole('textbox', { name: 'profilePage.spoolShelf.folderNamePlaceholder' });
    fireEvent.change(input, { target: { value: '  Dry box ' } });
    fireEvent.submit(input.closest('form')!);
    await waitFor(() => expect(api.createCollection).toHaveBeenCalledWith('Dry box'));
    await screen.findByRole('button', { name: /Dry box/ });

    fireEvent.click(screen.getAllByRole('button', { name: 'profilePage.spoolShelf.putInFolder' })[0]);
    const dialog = await screen.findByRole('dialog', { name: 'profilePage.spoolShelf.pickerTitle' });
    fireEvent.click(within(dialog).getByRole('checkbox', { name: 'Dry box' }));
    await waitFor(() => expect(api.updateCollectionMembers).toHaveBeenCalledWith(5, { add: [1] }));
    expect(within(dialog).getByRole('checkbox', { name: 'Dry box' })).toBeChecked();
  });

  it('asks before deleting a folder', async () => {
    folders = [{ id: 7, name: 'Silk', spool_count: 2 }];
    api.deleteCollection.mockResolvedValue(undefined);
    renderTab();

    fireEvent.click(await screen.findByRole('button', { name: /Silk/ }));
    await waitFor(() => expect(api.feed).toHaveBeenCalledWith(
      expect.objectContaining({ collection_id: 7 }),
      expect.anything(),
    ));
    fireEvent.click(screen.getByRole('button', { name: 'profilePage.spoolShelf.deleteFolder' }));
    expect(screen.getByText('profilePage.spoolShelf.deleteFolderMessage')).toBeInTheDocument();
    expect(api.deleteCollection).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'confirmDeleteModal.delete' }));
    await waitFor(() => expect(api.deleteCollection).toHaveBeenCalledWith(7));
  });
});
