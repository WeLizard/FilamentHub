import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Notification } from '../types/api';
import { DeletedPresetsModal } from './DeletedPresetsModal';

const mocks = vi.hoisted(() => ({ list: vi.fn(), handleAction: vi.fn() }));
vi.mock('../api/client', () => ({
  orcaslicerDeletedPresetsAPI: {
    list: (...args: unknown[]) => mocks.list(...args),
    handleAction: (...args: unknown[]) => mocks.handleAction(...args),
  },
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const notification: Notification = {
  id: 41,
  user_id: 7,
  type: 'preset_locally_deleted',
  title: 'preset_locally_deleted',
  message: 'preset_locally_deleted_message',
  link: null,
  extra_data: null,
  read: false,
  read_at: null,
  created_at: '2026-09-12T12:00:00Z',
};
const item = (id: number) => ({
  id,
  preset_id: id + 100,
  preset_name: `Preset ${id}`,
  bundle_preset_name: null,
  is_created: false,
  is_saved: true,
  reported_at: '2026-09-12T12:00:00Z',
});

function renderModal(onClose = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <DeletedPresetsModal isOpen onClose={onClose} notification={notification} />
    </QueryClientProvider>,
  );
  return { queryClient, onClose };
}

describe('DeletedPresetsModal durable queue', () => {
  beforeEach(() => vi.clearAllMocks());

  it('loads page two and applies an action to every server-side remaining item', async () => {
    mocks.list
      .mockResolvedValueOnce({ items: [item(1)], next_cursor: 1, remaining_count: 3, created_count: 0, saved_count: 3 })
      .mockResolvedValueOnce({ items: [item(2), item(3)], next_cursor: null, remaining_count: 3, created_count: 0, saved_count: 3 });
    mocks.handleAction.mockResolvedValue({ action: 'skip', total_count: 3, processed_count: 3 });
    renderModal();

    await screen.findByText('Preset 1');
    fireEvent.click(screen.getByRole('button', { name: 'deletedPresetsModal.load_more' }));
    expect(await screen.findByText('Preset 3')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: 'deletedPresetsModal.apply_all_remaining' }));
    fireEvent.click(screen.getByRole('button', { name: /deletedPresetsModal.action_skip_label/ }));
    fireEvent.click(screen.getByRole('button', { name: 'deletedPresetsModal.apply_button' }));

    await waitFor(() => expect(mocks.handleAction).toHaveBeenCalledWith(41, expect.objectContaining({
      action: 'skip', apply_to_all: true, preset_ids: null,
    })));
  });

  it('offers a truthful retry after the initial page fails', async () => {
    mocks.list
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ items: [item(1)], next_cursor: null, remaining_count: 1, created_count: 0, saved_count: 1 });
    renderModal();

    expect(await screen.findByRole('alert')).toHaveTextContent('deletedPresetsModal.load_error');
    fireEvent.click(screen.getByRole('button', { name: 'deletedPresetsModal.retry' }));
    expect(await screen.findByText('Preset 1')).toBeInTheDocument();
  });

  it('keeps loaded decisions visible when the next page fails and can retry it', async () => {
    mocks.list
      .mockResolvedValueOnce({ items: [item(1)], next_cursor: 1, remaining_count: 2, created_count: 0, saved_count: 2 })
      .mockRejectedValueOnce(new Error('page offline'))
      .mockResolvedValueOnce({ items: [item(2)], next_cursor: null, remaining_count: 2, created_count: 0, saved_count: 2 });
    renderModal();

    await screen.findByText('Preset 1');
    fireEvent.click(screen.getByRole('button', { name: 'deletedPresetsModal.load_more' }));
    expect(await screen.findByText('deletedPresetsModal.load_more_error')).toBeInTheDocument();
    expect(screen.getByText('Preset 1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'deletedPresetsModal.retry' }));
    expect(await screen.findByText('Preset 2')).toBeInTheDocument();
  });

  it('does not close or delete the notification merely because the server queue is empty', async () => {
    mocks.list.mockResolvedValue({ items: [], next_cursor: null, remaining_count: 0, created_count: 0, saved_count: 0 });
    const onClose = vi.fn();
    renderModal(onClose);

    expect(await screen.findByText('deletedPresetsModal.empty')).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(onClose).not.toHaveBeenCalled();
  });
});
