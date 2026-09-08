import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '../types/api';
import { SettingsTab } from './SettingsTab';

const mocks = vi.hoisted(() => ({
  refreshUser: vi.fn(),
  updateSettings: vi.fn(),
  updateEmail: vi.fn(),
  createReauthChallenge: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('../api/client', () => ({
  authAPI: {
    updateSettings: (...args: unknown[]) => mocks.updateSettings(...args),
    updateUsername: vi.fn(),
    updateProfile: vi.fn(),
    updatePassword: vi.fn(),
    updateEmail: (...args: unknown[]) => mocks.updateEmail(...args),
    updatePreferences: vi.fn(),
  },
  adminAPI: {
    createReauthChallenge: (...args: unknown[]) => mocks.createReauthChallenge(...args),
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ refreshUser: mocks.refreshUser }),
}));

vi.mock('../hooks/useUserCurrency', () => ({
  USER_PREFERENCES_QUERY_KEY: ['user-preferences'],
  useUserCurrency: () => ({ currency: 'USD' }),
}));

vi.mock('../utils/countries', () => ({ sortedCountries: () => [] }));
vi.mock('../utils/currency', () => ({
  currencyCodes: () => ['USD'],
  currencySymbol: () => '$',
}));
vi.mock('./DeleteAccountModal', () => ({ DeleteAccountModal: () => null }));
vi.mock('./LanguageSwitcher', () => ({ LanguageSwitcher: () => null }));
vi.mock('./ActiveSessions', () => ({
  ActiveSessions: ({ userId }: { userId: number }) => <div data-testid="active-sessions">{userId}</div>,
}));

const user = {
  id: 1,
  email: 'user@example.com',
  username: 'user',
  role: 'user',
  full_name: null,
  avatar_url: null,
  active: true,
  email_verified: true,
  brand_id: null,
  active_organization_id: null,
  brand_name: null,
  printer_id: null,
  recommend_physical_printer_id: null,
  recommend_printer_profile_id: null,
  oauth_provider: null,
  has_password: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  last_login: null,
  legal_onboarding_required: false,
  allow_filament_presets_import: true,
  allow_filament_presets_export: true,
  allow_printer_profiles_import: true,
  allow_printer_profiles_export: true,
  allow_print_profiles_import: true,
  allow_print_profiles_export: true,
  auto_import_local_presets: false,
  sync_printer_endpoints: false,
} satisfies User;

function renderSettings(currentUser: User = user) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <SettingsTab user={currentUser} onUserUpdate={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe('SettingsTab printer sync settings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.updateSettings.mockResolvedValue(user);
    mocks.updateEmail.mockResolvedValue({ message: 'sent' });
    mocks.createReauthChallenge.mockResolvedValue({
      challenge_id: 'challenge-1',
      expires_at: '2026-09-05T20:10:00Z',
      masked_email: 'u***@example.com',
    });
  });

  it('turns both printer profile permissions off in each direction and saves false values', async () => {
    renderSettings();

    const printerToHub = screen.getByRole('checkbox', { name: /settings\.syncPrinterToHubNote/ });
    const printerToSlicer = screen.getByRole('checkbox', { name: /settings\.syncPrinterToSlicerNote/ });

    expect(printerToHub).toBeChecked();
    expect(printerToSlicer).toBeChecked();

    fireEvent.click(printerToHub);
    fireEvent.click(printerToSlicer);

    expect(printerToHub).not.toBeChecked();
    expect(printerToSlicer).not.toBeChecked();

    fireEvent.click(screen.getByRole('button', { name: 'settings.save' }));

    await waitFor(() => expect(mocks.updateSettings).toHaveBeenCalledOnce());
    expect(mocks.updateSettings.mock.calls[0][0]).toEqual(expect.objectContaining({
      allow_printer_profiles_import: false,
      allow_print_profiles_import: false,
      allow_printer_profiles_export: false,
      allow_print_profiles_export: false,
    }));
  });

  it('shows browser sessions for the current account identity', () => {
    renderSettings();

    expect(screen.getByTestId('active-sessions')).toHaveTextContent('1');
  });

  it('keeps the ordinary user email change as a direct request', async () => {
    renderSettings();
    const emailRow = screen.getByText('user@example.com').closest<HTMLElement>('.p-4')!;
    fireEvent.click(within(emailRow).getByRole('button', { name: 'settings.edit' }));
    const input = within(emailRow).getByPlaceholderText('settings.newEmailPlaceholder');
    fireEvent.change(input, { target: { value: 'next@example.com' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => expect(mocks.updateEmail).toHaveBeenCalled());
    expect(mocks.updateEmail.mock.calls[0][0]).toEqual({
      new_email: 'next@example.com',
    });
    expect(mocks.createReauthChallenge).not.toHaveBeenCalled();
  });

  it('binds an administrator challenge to the new email before changing it', async () => {
    renderSettings({ ...user, role: 'admin' });
    const emailRow = screen.getByText('user@example.com').closest<HTMLElement>('.p-4')!;
    fireEvent.click(within(emailRow).getByRole('button', { name: 'settings.edit' }));
    const input = within(emailRow).getByPlaceholderText('settings.newEmailPlaceholder');
    fireEvent.change(input, { target: { value: 'admin-next@example.com' } });
    fireEvent.submit(input.closest('form')!);

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'adminConfirmation.sendCode' }));
    await waitFor(() => expect(mocks.createReauthChallenge).toHaveBeenCalledWith({
      action: 'change_admin_email',
      target_user_id: 1,
      new_email: 'admin-next@example.com',
    }));
    fireEvent.change(within(dialog).getByRole('textbox', { name: /adminConfirmation\.codeLabel/ }), {
      target: { value: '654321' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'settings.save' }));

    await waitFor(() => expect(mocks.updateEmail).toHaveBeenCalled());
    expect(mocks.updateEmail.mock.calls[0][0]).toEqual({
      new_email: 'admin-next@example.com',
      confirmation: { challenge_id: 'challenge-1', code: '654321' },
    });
  });
});
