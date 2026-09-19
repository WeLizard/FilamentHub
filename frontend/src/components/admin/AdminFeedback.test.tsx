import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { FeedbackDetail } from '../../types/api';
import { AdminFeedback } from './AdminFeedback';

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  downloadLog: vi.fn(),
  downloadBlob: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { emoji?: string }) =>
      options?.emoji ? `${key}:${options.emoji}` : key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('../../api/client', () => ({
  adminFeedbackAPI: {
    list: (...args: unknown[]) => mocks.list(...args),
    get: (...args: unknown[]) => mocks.get(...args),
    update: (...args: unknown[]) => mocks.update(...args),
    delete: (...args: unknown[]) => mocks.remove(...args),
    downloadPluginLog: (...args: unknown[]) => mocks.downloadLog(...args),
  },
}));

vi.mock('../../utils/download', () => ({ downloadBlob: mocks.downloadBlob }));

vi.mock('../Toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const feedback: FeedbackDetail = {
  id: 17,
  user_id: 4,
  user_username: 'jaxon',
  type: 'bug',
  subject: 'Screenshot upload',
  message: 'The upload button is missing.',
  email: null,
  source: 'general',
  source_url: null,
  source_id: null,
  status: 'open',
  admin_response: null,
  admin_response_at: null,
  responded_by: null,
  created_at: '2026-08-27T08:00:00Z',
  updated_at: '2026-08-27T08:00:00Z',
  messages: [
    {
      id: 1,
      author_user_id: 4,
      author_type: 'user',
      message: 'The upload button is missing.',
      created_at: '2026-08-27T08:00:00Z',
    },
  ],
};

function renderFeedback() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <AdminFeedback />
    </QueryClientProvider>,
  );
}

describe('AdminFeedback emoji picker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.list.mockResolvedValue({
      items: [feedback],
      total: 1,
      page: 1,
      size: 20,
      pages: 1,
    });
    mocks.get.mockResolvedValue(feedback);
  });

  it('inserts an emoji at the current selection in the response', async () => {
    renderFeedback();

    fireEvent.click(await screen.findByText(feedback.subject));

    const textarea = screen.getByPlaceholderText(
      'adminFeedback.modal_response_placeholder',
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'Hello world' } });
    textarea.setSelectionRange(6, 11);

    fireEvent.click(screen.getByRole('button', { name: 'adminFeedback.addEmoji' }));
    fireEvent.click(screen.getByRole('button', { name: 'adminFeedback.insertEmoji:👍' }));

    expect(textarea).toHaveValue('Hello 👍');
  });

  it('shows the account username instead of an internal numeric id', async () => {
    renderFeedback();

    expect(await screen.findByText(/jaxon/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(feedback.subject));
    expect(await screen.findAllByText(/jaxon/)).toHaveLength(2);
    expect(screen.queryByText(/User #4|Пользователь #4/)).not.toBeInTheDocument();
  });

  it('offers an attached plugin log only as a file download', async () => {
    const withLog = { ...feedback, plugin_log_size: 12_288 };
    const blob = new Blob(['FilamentHub plugin 0.2.0']);
    mocks.list.mockResolvedValue({ items: [withLog], total: 1, page: 1, size: 20, pages: 1 });
    mocks.get.mockResolvedValue(withLog);
    mocks.downloadLog.mockResolvedValue(blob);
    renderFeedback();

    fireEvent.click(await screen.findByText(feedback.subject));
    fireEvent.click(await screen.findByRole('button', { name: /adminFeedback.downloadPluginLog/ }));

    await waitFor(() => (
      expect(mocks.downloadBlob).toHaveBeenCalledWith(blob, 'feedback-17-plugin.log')
    ));
    expect(mocks.downloadLog).toHaveBeenCalledWith(17);
    expect(screen.queryByText('FilamentHub plugin 0.2.0')).not.toBeInTheDocument();
  });
});
