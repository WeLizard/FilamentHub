import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { FeedbackDetail, FeedbackStatus } from '../types/api';
import { FeedbackThreadPage } from './FeedbackThreadPage';

let feedbackStatus: FeedbackStatus = 'open';

const feedback: FeedbackDetail = {
  id: 17,
  user_id: 4,
  type: 'question',
  subject: 'OctoPrint slots',
  message: 'Are these physical gates?',
  email: null,
  source: null,
  source_url: null,
  source_id: null,
  status: 'open',
  admin_response: null,
  admin_response_at: null,
  responded_by: null,
  created_at: '2026-07-31T08:00:00Z',
  updated_at: '2026-07-31T08:00:00Z',
  messages: [
    {
      id: 1,
      author_user_id: 4,
      author_type: 'user',
      message: 'Are these physical gates?',
      created_at: '2026-07-31T08:00:00Z',
    },
  ],
};

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({ feedbackId: '17' }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', resolvedLanguage: 'en' },
  }),
}));

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({
    data: { ...feedback, status: feedbackStatus },
    isLoading: false,
    isError: false,
  }),
  useMutation: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
  useQueryClient: () => ({
    setQueryData: vi.fn(),
    invalidateQueries: vi.fn(),
  }),
}));

vi.mock('../api/client', () => ({
  feedbackAPI: {
    get: vi.fn(),
    reply: vi.fn(),
  },
}));

vi.mock('../components/Toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('FeedbackThreadPage', () => {
  beforeEach(() => {
    feedbackStatus = 'open';
  });

  it('allows replies while the feedback is open', () => {
    render(<FeedbackThreadPage />);

    expect(screen.getByLabelText('feedbackThread.replyLabel')).toBeInTheDocument();
    expect(screen.queryByText('feedbackThread.lockedTitle')).not.toBeInTheDocument();
  });

  it.each<FeedbackStatus>(['resolved', 'closed'])(
    'keeps a %s conversation readable but blocks replies',
    (status) => {
      feedbackStatus = status;
      render(<FeedbackThreadPage />);

      expect(screen.getByText('Are these physical gates?')).toBeInTheDocument();
      expect(screen.getByText('feedbackThread.lockedTitle')).toBeInTheDocument();
      expect(screen.queryByLabelText('feedbackThread.replyLabel')).not.toBeInTheDocument();
    },
  );
});
