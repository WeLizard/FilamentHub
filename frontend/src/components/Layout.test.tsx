import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { Layout } from './Layout';

const { scanQr } = vi.hoisted(() => ({ scanQr: vi.fn() }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: null, logout: vi.fn() }),
}));

vi.mock('../api/client', () => ({
  authAPI: { getPresetsStats: vi.fn() },
  qrAPI: { scan: scanQr },
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
vi.mock('./QrScannerModal', () => ({
  QrScannerModal: ({ onDetected }: { onDetected: (value: string) => Promise<boolean> }) => (
    <button type="button" onClick={() => void onDetected('https://filamenthub.ru/qr/FH-TEST')}>
      detect-qr
    </button>
  ),
}));
vi.mock('./QrScanResultModal', () => ({
  QrScanResultModal: ({ result }: { result: { filament: { id: number } } }) => (
    <div data-testid="qr-scan-result">{result.filament.id}</div>
  ),
}));

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

  it('shows the recognition result before a follow-up action', async () => {
    scanQr.mockResolvedValueOnce({
      filament: { id: 42, brand_name: 'QR Brand', name: 'Exact PLA' },
      preset_added: false,
      preset: null,
      preset_saved: null,
      preset_sync_enabled: null,
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          <Layout><span>content</span></Layout>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getAllByRole('button', { name: 'qrScanner.open' })[0]);
    fireEvent.click(await screen.findByRole('button', { name: 'detect-qr' }));

    expect(await screen.findByTestId('qr-scan-result')).toHaveTextContent('42');
    expect(scanQr).toHaveBeenCalledWith('FH-TEST');
  });
});
