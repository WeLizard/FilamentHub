import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { UserSpool } from '../api/client';
import { spoolQueryKeys } from '../utils/spoolQueries';

const api = vi.hoisted(() => ({ updateCollectionMembers: vi.fn() }));
vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));
vi.mock('./Toast', () => ({ toast: { error: vi.fn() } }));
vi.mock('../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/client')>();
  return { ...original, spoolsAPI: { ...original.spoolsAPI, ...api } };
});

import { SpoolFolderPicker } from './SpoolFolderPicker';

describe('SpoolFolderPicker', () => {
  it('refreshes the folder counters as soon as a spool is filed, not only on close', async () => {
    api.updateCollectionMembers.mockResolvedValue({ id: 5, name: 'Blue', spool_count: 1 });
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    render(
      <QueryClientProvider client={client}>
        <SpoolFolderPicker
          spool={{ id: 9, filament: null, extra: null, collection_ids: [] } as unknown as UserSpool}
          collections={[{ id: 5, name: 'Blue', spool_count: 0 }]}
          userId={1}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole('checkbox'));

    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: spoolQueryKeys.collections(1) }));
  });
});
