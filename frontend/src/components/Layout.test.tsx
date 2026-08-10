import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { Layout } from './Layout';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: null, logout: vi.fn() }),
}));

vi.mock('../api/client', () => ({
  authAPI: { getPresetsStats: vi.fn() },
  qrAPI: { scan: vi.fn() },
}));

vi.mock('../utils/pluginBridge', () => ({
  isPluginEmbed: () => false,
  reportAuthStateToPlugin: vi.fn(),
}));

vi.mock('./AuthModal', () => ({ AuthModal: () => null }));
vi.mock('./EmbedDebugOverlay', () => ({ EmbedDebugOverlay: () => null }));
vi.mock('./FeedbackModal', () => ({ FeedbackModal: () => null }));
vi.mock('./LanguageSwitcher', () => ({ LanguageSwitcher: () => null }));
vi.mock('./Notifications', () => ({ Notifications: () => null }));
vi.mock('./QrScannerModal', () => ({ QrScannerModal: () => null }));

describe('Layout', () => {
  it('keeps the steady-state background free from perpetual animation', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { container } = render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          <Layout><span>content</span></Layout>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(container.querySelectorAll('[class*="animate-"]')).toHaveLength(0);
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
  });
});
