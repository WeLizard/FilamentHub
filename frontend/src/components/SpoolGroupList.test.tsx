import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { SpoolGroup, UserSpool } from '../api/client';

const api = vi.hoisted(() => ({ groups: vi.fn(), feed: vi.fn() }));
vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));
vi.mock('../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/client')>();
  return { ...original, spoolsAPI: { ...original.spoolsAPI, ...api } };
});

import { SpoolGroupList } from './SpoolGroupList';

const spool = (id: number, brand: string | null): UserSpool => ({
  id,
  filament: brand ? { id: id, name: `${brand} PLA`, brand_name: brand, material_type: 'PLA' } : null,
  extra: null,
}) as unknown as UserSpool;

const group = (key: string, count: number, latest: UserSpool): SpoolGroup => ({
  key,
  spool_count: count,
  state_counts: { active: count, shelf: 0, archived: 0, empty: 0 },
  available_remaining_weight_g: 0,
  unknown_mass_count: 0,
  latest_spool: latest,
}) as SpoolGroup;

function renderList(groupBy: 'product' | 'brand' | 'type') {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <SpoolGroupList
        userId={1}
        filters={{}}
        groupBy={groupBy}
        viewMode="list"
        renderSpool={(item) => <div data-testid="card">{item.id}</div>}
      />
    </QueryClientProvider>,
  );
}

describe('SpoolGroupList folding', () => {
  it('asks the server for the chosen fold and names a manufacturer group after its brand', async () => {
    api.groups.mockResolvedValue({
      items: [group('b:3', 2, spool(1, 'Acme'))],
      next_cursor: null,
      summary: { total: 2, group_count: 1, available_remaining_weight_g: 0, unknown_mass_count: 0 },
    });
    renderList('brand');

    expect(await screen.findByText('Acme')).toBeInTheDocument();
    expect(api.groups.mock.calls[0][0]).toMatchObject({ group_by: 'brand' });
  });

  it('keeps a lone uncarded spool under its own header instead of a bare card', async () => {
    api.groups.mockResolvedValue({
      items: [group('f:1', 1, spool(1, 'Acme')), group('n:0', 1, spool(2, null))],
      next_cursor: null,
      summary: { total: 2, group_count: 2, available_remaining_weight_g: 0, unknown_mass_count: 0 },
    });
    renderList('product');

    await waitFor(() => expect(screen.getAllByTestId('card')).toHaveLength(1));
    expect(screen.getByText('profilePage.spoolShelf.noCatalogCard')).toBeInTheDocument();
  });
});
