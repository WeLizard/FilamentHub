import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import type { WikiRevision } from '../types/api';
import { WikiWorkspacePage } from './WikiWorkspacePage';

const mocks = vi.hoisted(() => ({
  listOwnRevisions: vi.fn(),
  listCategories: vi.fn(),
}));

vi.mock('../api/client', () => ({
  wikiAPI: {
    listOwnRevisions: mocks.listOwnRevisions,
    listCategories: mocks.listCategories,
    retryRevision: vi.fn(),
    withdrawRevision: vi.fn(),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: { page?: number; total?: number }) => (
      key === 'wikiWorkspace.page' ? `${values?.page}/${values?.total}` : key
    ),
    i18n: { resolvedLanguage: 'en' },
  }),
}));

vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));

vi.mock('../components/SEOHead', () => ({ SEOHead: () => null }));
vi.mock('../components/wiki', () => ({ WikiAuthoringModal: () => <div>authoring-modal</div> }));

const draft: WikiRevision = {
  id: 10,
  article_id: 20,
  article_category_id: 1,
  article_slug: 'workspace-draft',
  article_content_key: 'workspace-draft',
  article_title: 'Workspace draft',
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
  title: 'Workspace draft',
  summary: 'Summary',
  content: 'Content',
  tags: null,
  edit_summary: 'Continue this work',
  review_note: null,
  submitted_at: null,
  reviewed_at: null,
  published_at: null,
  created_at: '2026-08-02T00:00:00Z',
  updated_at: '2026-08-02T00:00:00Z',
  peer_reviews: [],
};

describe('WikiWorkspacePage', () => {
  it('loads private work with server pagination and opens a saved draft', async () => {
    mocks.listOwnRevisions.mockResolvedValue({
      items: [draft],
      total: 13,
      page: 1,
      page_size: 12,
      total_pages: 2,
    });
    mocks.listCategories.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, total_pages: 0 });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <WikiWorkspacePage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Workspace draft')).toBeInTheDocument();
    expect(mocks.listOwnRevisions).toHaveBeenCalledWith({ status: undefined, page: 1, page_size: 12 });

    fireEvent.click(screen.getByRole('button', { name: 'wikiWorkspace.continueEditing' }));
    expect(screen.getByText('authoring-modal')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'wikiWorkspace.next' }));
    await waitFor(() => expect(mocks.listOwnRevisions).toHaveBeenCalledWith({ status: undefined, page: 2, page_size: 12 }));
  });
});
