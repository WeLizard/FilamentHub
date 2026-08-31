import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { UserSpool } from '../api/client';
import { SpoolTagsButton } from './SpoolTagsButton';

const tagApi = vi.hoisted(() => ({
  list: vi.fn(),
  link: vi.fn(),
  unlink: vi.fn(),
}));

vi.mock('../api/client', () => ({ spoolTagsAPI: tagApi }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('./Toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock('./ModalOverlay', () => ({
  ModalOverlay: ({ children }: { children: ReactNode }) => (
    <div role="dialog">{children}</div>
  ),
}));

const spool: Pick<UserSpool, 'id' | 'filament'> = {
  id: 41,
  filament: null,
};

function renderButton() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SpoolTagsButton spool={spool} />
    </QueryClientProvider>,
  );
}

describe('spool physical tags', () => {
  beforeEach(() => {
    tagApi.list.mockReset().mockResolvedValue([]);
    tagApi.link.mockReset().mockResolvedValue({
      id: 1,
      spool_id: spool.id,
      uid: '04A1B2C3',
      technology: 'unknown',
      format: null,
      created_at: '2026-09-01T00:00:00Z',
      updated_at: '2026-09-01T00:00:00Z',
    });
    tagApi.unlink.mockReset().mockResolvedValue(undefined);
  });

  it('links a scanned UID to the FilamentHub spool without provider fields', async () => {
    renderButton();
    fireEvent.click(screen.getByRole('button', { name: 'spoolTags.action' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('spoolTags.uid'), {
      target: { value: '04:a1-b2:c3' },
    });
    fireEvent.submit(screen.getByRole('button', { name: 'spoolTags.link' }).closest('form')!);

    await waitFor(() => expect(tagApi.link).toHaveBeenCalledWith(41, {
      uid: '04:a1-b2:c3',
      technology: 'unknown',
      format: null,
    }));
  });

  it('lists and unlinks the canonical binding', async () => {
    tagApi.list.mockResolvedValue([{
      id: 9,
      spool_id: 41,
      uid: 'DEADBEEF',
      technology: 'uhf_rfid',
      format: 'epc-gen2',
      created_at: '2026-09-01T00:00:00Z',
      updated_at: '2026-09-01T00:00:00Z',
    }]);
    renderButton();
    fireEvent.click(screen.getByRole('button', { name: 'spoolTags.action' }));

    expect(await screen.findByText('DEADBEEF')).toBeInTheDocument();
    expect(screen.getByText('spoolTags.technologyLabel.uhf_rfid · epc-gen2')).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('spoolTags.unlink'));

    await waitFor(() => expect(tagApi.unlink).toHaveBeenCalledWith(41, 'DEADBEEF'));
  });
});
