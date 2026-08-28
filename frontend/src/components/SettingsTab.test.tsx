import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '../types/api';
import { SettingsTab } from './SettingsTab';

const mocks = vi.hoisted(() => ({
  refreshUser: vi.fn(),
  updateSettings: vi.fn(),
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
    updateEmail: vi.fn(),
    updatePreferences: vi.fn(),
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

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <SettingsTab user={user} onUserUpdate={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe('SettingsTab printer sync settings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.updateSettings.mockResolvedValue(user);
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
});
