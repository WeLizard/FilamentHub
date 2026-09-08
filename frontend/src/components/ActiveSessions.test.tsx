import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ActiveSessions } from './ActiveSessions';

const mocks = vi.hoisted(() => ({
  listSessions: vi.fn(),
  revokeSession: vi.fn(),
  revokeOtherSessions: vi.fn(),
}));

vi.mock('../api/client', () => ({
  authAPI: {
    listSessions: (...args: unknown[]) => mocks.listSessions(...args),
    revokeSession: (...args: unknown[]) => mocks.revokeSession(...args),
    revokeOtherSessions: (...args: unknown[]) => mocks.revokeOtherSessions(...args),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) => {
      if (!values) return key;
      return Object.entries(values).reduce(
        (text, [name, value]) => text.replace(`{{${name}}}`, String(value)),
        key,
      );
    },
  }),
}));

const current = {
  id: 'current', is_current: true,
  created_at: '2026-09-08T08:00:00Z', last_seen_at: '2026-09-08T12:00:00Z', expires_at: '2026-10-08T12:00:00Z',
  browser: 'chrome', os: 'windows', device_type: 'desktop',
} as const;
const other = {
  id: 'other', is_current: false,
  created_at: '2026-09-07T08:00:00Z', last_seen_at: '2026-09-08T11:30:00Z', expires_at: '2026-10-07T08:00:00Z',
  browser: 'safari', os: 'ios', device_type: 'mobile',
} as const;
const tablet = {
  id: 'tablet', is_current: false,
  created_at: '2026-09-06T08:00:00Z', last_seen_at: '2026-09-06T12:00:00Z', expires_at: '2026-10-06T08:00:00Z',
  browser: 'firefox', os: 'android', device_type: 'tablet',
} as const;

function renderSessions(userId = 7) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <ActiveSessions userId={userId} />
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
}

describe('ActiveSessions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.setSystemTime(new Date('2026-09-08T12:00:00Z'));
    mocks.revokeSession.mockResolvedValue({ revoked: true, current_session_revoked: false });
    mocks.revokeOtherSessions.mockResolvedValue({ revoked_count: 2 });
  });

  it('loads more privacy-safe rows and only allows other sessions to be ended', async () => {
    mocks.listSessions.mockImplementation(({ page }: { page: number }) => Promise.resolve(page === 1
      ? { items: [current, other], total: 3, page: 1, size: 10, pages: 2, current_session_id: 'current' }
      : { items: [tablet], total: 3, page: 2, size: 10, pages: 2, current_session_id: 'current' }));
    renderSessions();

    const currentRow = (await screen.findByText(/settings\.activeSessions\.current/)).closest('.p-4')!;
    expect(currentRow).toHaveTextContent('settings.activeSessions.browser.chrome');
    expect(within(currentRow as HTMLElement).queryByRole('button', { name: /settings.activeSessions.revokeNamed/ })).not.toBeInTheDocument();
    expect(screen.getByText('settings.activeSessions.connectedAppsSeparate')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'settings.activeSessions.loadMore' }));
    expect(await screen.findByText(/settings.activeSessions.browser.firefox/)).toBeInTheDocument();
    expect(mocks.listSessions).toHaveBeenCalledWith({ page: 2, size: 10 }, expect.any(AbortSignal));

    fireEvent.click(screen.getAllByRole('button', { name: /settings.activeSessions.revokeNamed/ })[0]);
    await waitFor(() => expect(mocks.revokeSession.mock.calls[0]?.[0]).toBe('other'));
    const revokeOthersButton = screen.getByRole('button', { name: 'settings.activeSessions.revokeOthers' });
    await waitFor(() => expect(revokeOthersButton).toBeEnabled());
    fireEvent.click(revokeOthersButton);
    await waitFor(() => expect(mocks.revokeOtherSessions).toHaveBeenCalledOnce());
  });

  it('keeps the previous list visible when a manual refresh fails', async () => {
    mocks.listSessions.mockResolvedValueOnce({
      items: [current, other], total: 2, page: 1, size: 10, pages: 1, current_session_id: 'current',
    });
    renderSessions();
    await screen.findByText(/settings.activeSessions.browser.safari/);
    mocks.listSessions.mockRejectedValueOnce(new Error('offline'));

    fireEvent.click(screen.getByRole('button', { name: 'settings.activeSessions.refresh' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('settings.activeSessions.refreshError');
    expect(screen.getByText(/settings.activeSessions.browser.safari/)).toBeInTheDocument();
  });

  it('cancels the previous account read when the identity key changes', async () => {
    let firstSignal: AbortSignal | undefined;
    mocks.listSessions
      .mockImplementationOnce((_params: unknown, signal: AbortSignal) => {
        firstSignal = signal;
        return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))));
      })
      .mockResolvedValueOnce({ items: [current], total: 1, page: 1, size: 10, pages: 1, current_session_id: 'current' });
    const view = renderSessions(7);
    await waitFor(() => expect(firstSignal).toBeDefined());

    view.rerender(
      <QueryClientProvider client={view.queryClient}>
        <ActiveSessions userId={8} />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(firstSignal?.aborted).toBe(true));
    expect(await screen.findByText(/settings\.activeSessions\.current/)).toBeInTheDocument();
  });
});
