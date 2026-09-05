import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Layout } from './Layout';

const { scanQr, authState } = vi.hoisted(() => ({
  scanQr: vi.fn(),
  authState: {
    user: null as null | { id: number; username: string; role: string },
    login: vi.fn(), register: vi.fn(), logout: vi.fn(),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => authState,
}));

vi.mock('../api/client', () => ({
  authAPI: {
    getPresetsStats: vi.fn(),
    getAuthMethods: vi.fn().mockResolvedValue({ oauth_providers: [], registration_captcha: 'disabled' }),
  },
  qrAPI: { scan: scanQr },
}));

vi.mock('../utils/pluginBridge', () => ({
  isPluginEmbed: () => false,
  reportAuthStateToPlugin: vi.fn(),
  startPluginOAuth: vi.fn(),
}));

vi.mock('./Captcha', () => ({ Recaptcha: () => null, getRecaptchaToken: vi.fn() }));
vi.mock('./ForgotPasswordModal', () => ({ ForgotPasswordModal: () => null }));
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
  QrScanResultModal: ({
    result,
    onAddSpool,
  }: {
    result: { filament: { id: number } };
    onAddSpool: (placement: 'shelf' | 'printer') => void;
  }) => (
    <div data-testid="qr-scan-result">
      {result.filament.id}
      <button type="button" onClick={() => onAddSpool('printer')}>add-to-printer</button>
    </div>
  ),
}));

const LocationProbe = () => {
  const location = useLocation();
  return <span data-testid="location">{`${location.pathname}${location.search}`}</span>;
};

describe('Layout', () => {
  beforeEach(() => {
    authState.user = null;
    authState.login.mockReset();
  });

  const renderReturnLogin = () => {
    let commitUser: () => void = () => {};
    const Harness = () => {
      const [user, setUser] = useState<typeof authState.user>(null);
      authState.user = user;
      commitUser = () => setUser({ id: 7, username: 'return-user', role: 'user' });
      return <Layout><LocationProbe /></Layout>;
    };
    authState.login.mockImplementation(async () => { commitUser(); });
    render(
      <MemoryRouter initialEntries={['/?auth=login&return_url=%2Fprofile%3Ftab%3Dspools']}>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <Harness />
        </QueryClientProvider>
      </MemoryRouter>,
    );
    return { commitUser: () => commitUser() };
  };

  it('returns to the requested page after successful login before the user render commits', async () => {
    renderReturnLogin();
    const email = await screen.findByPlaceholderText('authModal.placeholder_email_or_login');
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/'));
    fireEvent.change(email, { target: { value: 'return@example.test' } });
    fireEvent.change(screen.getByPlaceholderText('authModal.placeholder_password'), { target: { value: 'password' } });
    fireEvent.submit(email.closest('form')!);
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/profile?tab=spools'));
  });

  it('discards the return page when login is cancelled', async () => {
    const { commitUser } = renderReturnLogin();
    await screen.findByPlaceholderText('authModal.placeholder_email_or_login');
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/'));
    fireEvent.keyDown(document, { key: 'Escape' });
    act(() => commitUser());
    expect(screen.getByTestId('location').textContent).toBe('/');
  });

  it('keeps the steady-state background free from perpetual animation', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { container } = render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          <Layout><LocationProbe /></Layout>
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
          <Layout><LocationProbe /></Layout>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getAllByRole('button', { name: 'qrScanner.open' })[0]);
    fireEvent.click(await screen.findByRole('button', { name: 'detect-qr' }));

    expect(await screen.findByTestId('qr-scan-result')).toHaveTextContent('42');
    expect(scanQr).toHaveBeenCalledWith('FH-TEST');
    fireEvent.click(screen.getByRole('button', { name: 'add-to-printer' }));
    expect(screen.getByTestId('location')).toHaveTextContent(
      '/profile?tab=spools&add_spool=1&filament_id=42&source=qr&placement=printer',
    );
  });
});
