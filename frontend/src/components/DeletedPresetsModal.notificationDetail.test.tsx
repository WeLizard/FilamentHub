import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Notification } from '../types/api';
import { DeletedPresetsModal } from './DeletedPresetsModal';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  delete: vi.fn(),
  handleAction: vi.fn(),
}));

vi.mock('../api/client', () => ({
  notificationsAPI: {
    get: (...args: unknown[]) => mocks.get(...args),
    delete: (...args: unknown[]) => mocks.delete(...args),
  },
  orcaslicerDeletedPresetsAPI: {
    handleAction: (...args: unknown[]) => mocks.handleAction(...args),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const initialNotification: Notification = {
  id: 41,
  user_id: 7,
  type: 'preset_locally_deleted',
  title: 'preset_locally_deleted',
  message: 'preset_locally_deleted_message',
  link: null,
  extra_data: {
    deleted_presets: [{
      preset_id: 3,
      preset_name: 'PLA profile',
      is_created: true,
      is_saved: false,
    }],
  },
  read: false,
  read_at: null,
  created_at: '2026-09-12T12:00:00Z',
};

describe('DeletedPresetsModal notification detail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.get.mockResolvedValue({ ...initialNotification, read: true });
  });

  it('keeps notification detail out of the infinite feed cache', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <DeletedPresetsModal
          isOpen
          onClose={vi.fn()}
          notification={initialNotification}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(41, expect.any(AbortSignal)));
    await waitFor(() => {
      expect(queryClient.getQueryData<Notification>(['notification', 41])?.read).toBe(true);
    });
    expect(queryClient.getQueryData(['notifications', 7])).toBeUndefined();
  });
});
