import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { FileText } from 'lucide-react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { LegalDocumentPage } from './LegalDocumentPage';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'ru', resolvedLanguage: 'ru' },
  }),
}));

vi.mock('../api/client', () => ({
  authAPI: {
    getLegalDocument: vi.fn(() => new Promise(() => {})),
  },
}));

vi.mock('./SEOHead', () => ({ SEOHead: () => null }));

describe('LegalDocumentPage', () => {
  it('keeps the decorative background free from perpetual animation', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { container } = render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          <LegalDocumentPage
            documentType="privacy_policy"
            route="/privacy-policy"
            fallbackTitleKey="legal.privacyPolicy"
            icon={FileText}
            iconClassName="from-purple-600 to-pink-600"
          />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    const background = container.querySelector('[aria-hidden="true"]');
    expect(background).toBeInTheDocument();
    expect(background?.querySelectorAll('[class*="animate-"]')).toHaveLength(0);
  });
});
