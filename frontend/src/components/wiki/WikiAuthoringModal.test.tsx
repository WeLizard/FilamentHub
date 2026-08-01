import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { WikiCategory, WikiRevision } from '../../types/api';
import { WikiAuthoringModal } from './WikiAuthoringModal';

const mocks = vi.hoisted(() => ({
  createAuthoredArticle: vi.fn(),
  updateRevision: vi.fn(),
  submitRevision: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));

vi.mock('../../api/client', () => ({
  wikiAPI: {
    createAuthoredArticle: mocks.createAuthoredArticle,
    createRevision: vi.fn(),
    updateRevision: mocks.updateRevision,
    submitRevision: mocks.submitRevision,
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { resolvedLanguage: 'en' },
  }),
}));

vi.mock('../ModalOverlay', () => ({
  ModalOverlay: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('../Toast', () => ({
  toast: {
    error: mocks.toastError,
    success: mocks.toastSuccess,
  },
}));

vi.mock('./WikiContentRenderer', () => ({
  WikiContentRenderer: ({ content }: { content: string }) => <div>{content}</div>,
}));

const category: WikiCategory = {
  id: 1,
  name: 'Materials',
  slug: 'materials',
  description: 'Materials',
  icon: null,
  order: 0,
  created_at: '2026-08-02T00:00:00Z',
  updated_at: '2026-08-02T00:00:00Z',
  articles_count: 0,
};

const draft: WikiRevision = {
  id: 10,
  article_id: 20,
  article_category_id: 1,
  article_slug: 'safe-draft',
  article_title: 'Safe draft',
  article_space_key: 'knowledge',
  article_language: 'en',
  article_provenance: 'community',
  revision_number: 1,
  base_revision_id: null,
  base_title: null,
  base_summary: null,
  base_content: null,
  base_tags: null,
  created_by_id: 1,
  created_by_username: 'author',
  reviewed_by_id: null,
  reviewed_by_username: null,
  status: 'draft',
  authorship: 'community',
  title: 'Safe draft',
  summary: 'Summary',
  content: 'Content',
  tags: null,
  edit_summary: null,
  review_note: null,
  submitted_at: null,
  reviewed_at: null,
  published_at: null,
  created_at: '2026-08-02T00:00:00Z',
  updated_at: '2026-08-02T00:00:00Z',
  peer_reviews: [],
};

describe('WikiAuthoringModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.createAuthoredArticle.mockResolvedValue(draft);
    mocks.updateRevision.mockResolvedValue(draft);
  });

  it('reuses the saved draft when submission fails and the author retries', async () => {
    mocks.submitRevision
      .mockRejectedValueOnce(new Error('temporary failure'))
      .mockResolvedValueOnce({ ...draft, status: 'pending_review' });
    const onClose = vi.fn();
    const onSaved = vi.fn();

    render(
      <WikiAuthoringModal
        categories={[category]}
        onClose={onClose}
        onSaved={onSaved}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText('wikiAuthoring.titlePlaceholder'), { target: { value: 'Safe draft' } });
    fireEvent.change(screen.getByPlaceholderText('wikiAuthoring.summaryPlaceholder'), { target: { value: 'Summary' } });
    fireEvent.change(screen.getByPlaceholderText('wikiAuthoring.contentPlaceholder'), { target: { value: 'Content' } });
    fireEvent.click(screen.getByRole('button', { name: /wikiAuthoring.sendForReview/ }));

    await waitFor(() => expect(mocks.submitRevision).toHaveBeenCalledTimes(1));
    expect(mocks.createAuthoredArticle).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /wikiAuthoring.sendForReview/ }));

    await waitFor(() => expect(mocks.submitRevision).toHaveBeenCalledTimes(2));
    expect(mocks.createAuthoredArticle).toHaveBeenCalledTimes(1);
    expect(mocks.updateRevision).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
