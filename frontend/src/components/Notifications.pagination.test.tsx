import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Notification, NotificationFeedResponse } from '../types/api';
import { Notifications } from './Notifications';

const mocks = vi.hoisted(() => ({
  listFeed: vi.fn(),
  markAsRead: vi.fn(),
  markAllAsRead: vi.fn(),
  delete: vi.fn(),
  deleteAll: vi.fn(),
  refreshUser: vi.fn(),
}));

vi.mock('../api/client', () => ({
  notificationsAPI: {
    listFeed: (...args: unknown[]) => mocks.listFeed(...args),
    markAsRead: (...args: unknown[]) => mocks.markAsRead(...args),
    markAllAsRead: (...args: unknown[]) => mocks.markAllAsRead(...args),
    delete: (...args: unknown[]) => mocks.delete(...args),
    deleteAll: (...args: unknown[]) => mocks.deleteAll(...args),
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 7 }, refreshUser: mocks.refreshUser }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', resolvedLanguage: 'en' },
  }),
}));

vi.mock('./DeletedPresetsModal', () => ({
  DeletedPresetsModal: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div data-testid="deleted-presets-modal" /> : null,
}));

function notification(id: number, title: string): Notification {
  return {
    id,
    user_id: 7,
    type: 'admin_message',
    title,
    message: `${title} message`,
    link: null,
    extra_data: null,
    read: true,
    read_at: null,
    created_at: '2026-09-12T12:00:00Z',
  };
}

function renderNotifications(floating: boolean) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <Notifications floating={floating} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return queryClient;
}

describe('Notifications cursor feed', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.markAsRead.mockResolvedValue({});
    mocks.markAllAsRead.mockResolvedValue({ marked_count: 0, skipped_pending_count: 0 });
    mocks.delete.mockResolvedValue({ message: 'notification_deleted' });
    mocks.deleteAll.mockResolvedValue({
      deleted_count: 0,
      skipped_pending_count: 0,
      message: 'notifications_deleted',
    });
  });

  it.each([false, true])('loads and keeps older notifications in the %s panel', async (floating) => {
    const firstPage: NotificationFeedResponse = {
      items: [notification(11, 'Newest')],
      next_cursor: 11,
      unread_count: 0,
    };
    const secondPage: NotificationFeedResponse = {
      items: [notification(10, 'Older')],
      next_cursor: null,
      unread_count: 0,
    };
    mocks.listFeed.mockImplementation(({ cursor }: { cursor?: number }) =>
      Promise.resolve(cursor === 11 ? secondPage : firstPage));
    const queryClient = renderNotifications(floating);

    fireEvent.click(screen.getByRole('button', { name: 'notifications.title' }));
    expect(await screen.findByText('Newest')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'notifications.loadMore' }));

    expect(await screen.findByText('Older')).toBeInTheDocument();
    expect(screen.getByText('Newest')).toBeInTheDocument();
    expect(mocks.listFeed).toHaveBeenLastCalledWith(
      { limit: 50, cursor: 11 },
      expect.any(AbortSignal),
    );
    await waitFor(() => {
      const cached = queryClient.getQueryData<{ pages: NotificationFeedResponse[] }>([
        'notifications',
        7,
      ]);
      expect(cached?.pages).toHaveLength(2);
    });
  });

  it('keeps the loaded page visible when loading the next page fails', async () => {
    mocks.listFeed
      .mockResolvedValueOnce({
        items: [notification(11, 'Still visible')],
        next_cursor: 11,
        unread_count: 0,
      })
      .mockRejectedValueOnce(new Error('offline'));
    renderNotifications(false);

    fireEvent.click(screen.getByRole('button', { name: 'notifications.title' }));
    expect(await screen.findByText('Still visible')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'notifications.loadMore' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('notifications.loadMoreError');
    expect(screen.getByText('Still visible')).toBeInTheDocument();
  });

  it('uses the shell popover contract and mobile-sized notification actions', async () => {
    mocks.listFeed.mockResolvedValue({
      items: [notification(11, 'Newest')],
      next_cursor: null,
      unread_count: 0,
    });
    renderNotifications(false);

    const trigger = screen.getByRole('button', { name: 'notifications.title' });
    expect(trigger).toHaveClass('h-11', 'w-11');
    fireEvent.click(trigger);

    const panel = await screen.findByRole('region', { name: 'notifications.title' });
    expect(panel).toHaveClass('app-shell-header-popover');
    const row = (await screen.findByText('Newest')).closest('[class*="cursor-pointer"]');
    expect(row).toHaveClass('min-h-11');
    expect(screen.getByRole('button', { name: 'notifications.deleteOne' })).toHaveClass(
      'h-11',
      'w-11',
    );

    fireEvent.click(row!);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('button', { name: 'notifications.delete' })).toHaveClass(
      'min-h-11',
    );
    expect(within(dialog).getByRole('button', { name: 'common.close' })).toHaveClass(
      'h-11',
      'w-11',
    );
  });

  it('opens a pending deleted-preset decision without marking it read', async () => {
    mocks.listFeed.mockResolvedValue({
      items: [{
        ...notification(12, 'Deleted locally'),
        type: 'preset_locally_deleted',
        read: false,
      }],
      next_cursor: null,
      unread_count: 1,
    });
    renderNotifications(false);

    fireEvent.click(screen.getByRole('button', { name: 'notifications.title' }));
    const pendingRow = await screen.findByText('Deleted locally');
    expect(screen.queryByRole('button', { name: 'notifications.deleteOne' })).not.toBeInTheDocument();
    fireEvent.click(pendingRow);

    expect(await screen.findByTestId('deleted-presets-modal')).toBeInTheDocument();
    expect(mocks.markAsRead).not.toHaveBeenCalled();
  });
});
