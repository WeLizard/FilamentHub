/** Компонент вкладки настроек пользователя */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Settings, Lock, Mail, Save, CheckCircle, XCircle, Loader2, User as UserIcon, Eye, EyeOff, AlertTriangle, Trash2, Globe, Pencil } from 'lucide-react';
import { authAPI } from '../api/client';
import { currencySymbol, currencyCodes } from '../utils/currency';
import { sortedCountries } from '../utils/countries';
import { translateApiError } from '../utils/translateApiError';
import type { User } from '../types/api';
import { useAuth } from '../contexts/AuthContext';
import { USER_PREFERENCES_QUERY_KEY, useUserCurrency } from '../hooks/useUserCurrency';
import { DeleteAccountModal } from './DeleteAccountModal';
import { LanguageSwitcher } from './LanguageSwitcher';
import type { AxiosError } from 'axios';

interface SettingsTabProps {
  user: User;
  onUserUpdate: () => void;
}

type SyncSettingKey =
  | 'allow_filament_presets_import'
  | 'allow_filament_presets_export'
  | 'allow_printer_profiles_import'
  | 'allow_printer_profiles_export'
  | 'allow_print_profiles_import'
  | 'allow_print_profiles_export'
  | 'auto_import_local_presets'
  | 'sync_printer_endpoints';

// A printer is the machine, its configurations and their print processes, so one
// switch covers all three in each direction. A printer without its processes is
// half a printer, so installing one into the slicer is never split in two.
const SYNC_CONTOURS: {
  id: string;
  titleKey: string;
  hintKey: string;
  directions: {
    labelKey: string;
    noteKey?: string;
    keys: SyncSettingKey[];
    available: boolean;
  }[];
}[] = [
  {
    id: 'filament',
    titleKey: 'settings.syncFilamentTitle',
    hintKey: 'settings.syncFilamentHint',
    directions: [
      {
        labelKey: 'settings.syncToHub',
        noteKey: 'settings.syncFilamentToHubNote',
        keys: ['allow_filament_presets_import'],
        available: true,
      },
      {
        labelKey: 'settings.syncToSlicer',
        noteKey: 'settings.syncFilamentToSlicerNote',
        keys: ['allow_filament_presets_export'],
        available: true,
      },
      // Own presets are a separate consent: the two switches above move presets
      // the site already knows about, this one hands over work it never saw.
      {
        labelKey: 'settings.autoImportLocal',
        noteKey: 'settings.autoImportLocalHint',
        keys: ['auto_import_local_presets'],
        available: true,
      },
    ],
  },
  {
    id: 'printer',
    titleKey: 'settings.syncPrinterTitle',
    hintKey: 'settings.syncPrinterHint',
    directions: [
      {
        labelKey: 'settings.syncToHub',
        noteKey: 'settings.syncPrinterToHubNote',
        keys: ['allow_printer_profiles_import', 'allow_print_profiles_import'],
        available: true,
      },
      {
        labelKey: 'settings.syncToSlicer',
        noteKey: 'settings.syncPrinterToSlicerNote',
        keys: ['allow_printer_profiles_export', 'allow_print_profiles_export'],
        available: true,
      },
    ],
  },
];

export const SettingsTab: React.FC<SettingsTabProps> = ({ user, onUserUpdate }) => {
  const queryClient = useQueryClient();
  const { refreshUser } = useAuth();
  const { t, i18n } = useTranslation();

  // Состояние для модалки удаления аккаунта
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  // Состояния для настроек синхронизации
  const [syncSettings, setSyncSettings] = useState({
    allow_filament_presets_import: user.allow_filament_presets_import ?? true,
    allow_filament_presets_export: user.allow_filament_presets_export ?? true,
    allow_printer_profiles_import: user.allow_printer_profiles_import ?? true,
    allow_printer_profiles_export: user.allow_printer_profiles_export ?? true,
    allow_print_profiles_import: user.allow_print_profiles_import ?? true,
    allow_print_profiles_export: user.allow_print_profiles_export ?? true,
    auto_import_local_presets: user.auto_import_local_presets ?? false,
    sync_printer_endpoints: user.sync_printer_endpoints ?? false,
  });

  // Состояния для формы изменения username
  const [usernameForm, setUsernameForm] = useState({
    new_username: user.username,
  });
  const [usernameError, setUsernameError] = useState<string | null>(null);
  const [usernameSuccess, setUsernameSuccess] = useState(false);
  const [isUsernameEditing, setIsUsernameEditing] = useState(false);

  // Имя из OAuth — обычное поле профиля: пользователь может исправить или удалить его.
  const [fullNameForm, setFullNameForm] = useState(user.full_name ?? '');
  const [fullNameError, setFullNameError] = useState<string | null>(null);
  const [fullNameSuccess, setFullNameSuccess] = useState(false);
  const [isFullNameEditing, setIsFullNameEditing] = useState(false);

  // Состояния для формы изменения пароля
  const [passwordForm, setPasswordForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  });
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState(false);
  const [isPasswordEditing, setIsPasswordEditing] = useState(false);
  const [showPasswords, setShowPasswords] = useState({
    current: false,
    new: false,
    confirm: false,
  });

  // Состояния для формы изменения email
  const [emailForm, setEmailForm] = useState({
    new_email: user.email,
  });
  const [emailError, setEmailError] = useState<string | null>(null);
  const [emailSuccess, setEmailSuccess] = useState(false);
  const [isEmailEditing, setIsEmailEditing] = useState(false);

  // Мутация для обновления настроек
  const updateSettingsMutation = useMutation({
    mutationFn: authAPI.updateSettings,
    onSuccess: () => {
      refreshUser();
      queryClient.invalidateQueries({ queryKey: ['user'] });
    },
  });

  // Мутация для изменения username
  const updateUsernameMutation = useMutation({
    mutationFn: authAPI.updateUsername,
    onSuccess: () => {
      setUsernameSuccess(true);
      setIsUsernameEditing(false);
      setUsernameError(null);
      refreshUser();
      queryClient.invalidateQueries({ queryKey: ['user'] });
      setTimeout(() => setUsernameSuccess(false), 3000);
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      setUsernameError(translateApiError(t, error.response?.data?.detail, t('settings.usernameChangeError')));
      setUsernameSuccess(false);
    },
  });

  const updateFullNameMutation = useMutation({
    mutationFn: (fullName: string | null) => authAPI.updateProfile({ full_name: fullName }),
    onSuccess: async () => {
      setFullNameSuccess(true);
      setIsFullNameEditing(false);
      setFullNameError(null);
      await refreshUser();
      onUserUpdate();
      queryClient.invalidateQueries({ queryKey: ['user'] });
      setTimeout(() => setFullNameSuccess(false), 3000);
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      setFullNameError(translateApiError(t, error.response?.data?.detail, t('settings.fullNameChangeError')));
      setFullNameSuccess(false);
    },
  });

  // Мутация для изменения пароля
  const updatePasswordMutation = useMutation({
    mutationFn: authAPI.updatePassword,
    onSuccess: () => {
      setPasswordSuccess(true);
      setIsPasswordEditing(false);
      setPasswordForm({ current_password: '', new_password: '', confirm_password: '' });
      setPasswordError(null);
      setTimeout(() => setPasswordSuccess(false), 3000);
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      setPasswordError(translateApiError(t, error.response?.data?.detail, t('settings.passwordChangeError')));
      setPasswordSuccess(false);
    },
  });

  // Мутация для изменения email
  const updateEmailMutation = useMutation({
    mutationFn: authAPI.updateEmail,
    onSuccess: () => {
      setEmailSuccess(true);
      setIsEmailEditing(false);
      setEmailError(null);
      // Email не меняется сразу — показываем сообщение "проверьте почту"
      // Не вызываем refreshUser() — email ещё не изменён
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      setEmailError(translateApiError(t, error.response?.data?.detail, t('settings.emailChangeError')));
      setEmailSuccess(false);
    },
  });

  const handleSyncSettingsChange = (key: keyof typeof syncSettings, value: boolean) => {
    setSyncSettings((prev) => ({ ...prev, [key]: value }));
  };

  const handleSaveSyncSettings = async () => {
    try {
      await updateSettingsMutation.mutateAsync(syncSettings);
    } catch (error) {
      // Ошибка обрабатывается в onError мутации
    }
  };

  const handleUsernameSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setUsernameError(null);
    setUsernameSuccess(false);

    // Валидация
    if (usernameForm.new_username.length < 3) {
      setUsernameError(t('settings.usernameMinLength'));
      return;
    }

    if (usernameForm.new_username === user.username) {
      setUsernameError(t('settings.usernameMustDiffer'));
      return;
    }

    try {
      await updateUsernameMutation.mutateAsync({
        new_username: usernameForm.new_username,
      });
    } catch (error) {
      // Ошибка обрабатывается в onError мутации
    }
  };

  const handleFullNameSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFullNameError(null);
    setFullNameSuccess(false);

    const normalizedFullName = fullNameForm.trim();
    if (normalizedFullName === (user.full_name ?? '')) {
      setFullNameError(t('settings.fullNameMustDiffer'));
      return;
    }

    try {
      await updateFullNameMutation.mutateAsync(normalizedFullName || null);
    } catch (error) {
      // Ошибка обрабатывается в onError мутации
    }
  };

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError(null);
    setPasswordSuccess(false);

    // Валидация текущего пароля — только если он есть у пользователя
    if (user.has_password && passwordForm.current_password.length === 0) {
      setPasswordError(t('settings.enterCurrentPassword'));
      return;
    }

    if (passwordForm.new_password.length < 8) {
      setPasswordError(t('settings.passwordMinLength'));
      return;
    }

    if (!/[a-zA-Zа-яА-ЯёЁ]/.test(passwordForm.new_password)) {
      setPasswordError(t('settings.passwordNeedLetter'));
      return;
    }

    if (!/\d/.test(passwordForm.new_password)) {
      setPasswordError(t('settings.passwordNeedDigit'));
      return;
    }

    if (passwordForm.new_password !== passwordForm.confirm_password) {
      setPasswordError(t('settings.passwordsMismatch'));
      return;
    }

    if (user.has_password && passwordForm.current_password === passwordForm.new_password) {
      setPasswordError(t('settings.passwordMustDiffer'));
      return;
    }

    try {
      await updatePasswordMutation.mutateAsync({
        current_password: user.has_password ? passwordForm.current_password : undefined,
        new_password: passwordForm.new_password,
      });
    } catch (error) {
      // Ошибка обрабатывается в onError мутации
    }
  };

  const handleEmailSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setEmailError(null);
    setEmailSuccess(false);

    // Валидация
    if (!emailForm.new_email || !emailForm.new_email.includes('@')) {
      setEmailError(t('settings.invalidEmail'));
      return;
    }

    if (emailForm.new_email === user.email) {
      setEmailError(t('settings.emailMustDiffer'));
      return;
    }

    try {
      await updateEmailMutation.mutateAsync({
        new_email: emailForm.new_email,
      });
    } catch (error) {
      // Ошибка обрабатывается в onError мутации
    }
  };

  const { currency } = useUserCurrency();
  const updateCurrencyMutation = useMutation({
    mutationFn: (code: string) => authAPI.updatePreferences({ currency: code }),
    onSuccess: (preferences) => {
      queryClient.setQueryData(USER_PREFERENCES_QUERY_KEY, preferences);
      queryClient.invalidateQueries({ queryKey: ['calculator-profile'] });
    },
  });

  const countryOptions = useMemo(() => sortedCountries(i18n.language), [i18n.language]);
  const updateCountryMutation = useMutation({
    mutationFn: (code: string) => authAPI.updateProfile({ country: code || null }),
    onSuccess: () => {
      refreshUser();
      onUserUpdate();
    },
  });

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <div className="grid grid-cols-1 overflow-hidden rounded-[1.75rem] border border-white/10 bg-slate-950/55 shadow-2xl shadow-black/20 lg:grid-cols-2">
      {/* Язык, валюта и страна */}
      <section className="order-2 border-t border-white/10 p-5 md:p-6 lg:border-l lg:border-t-0">
        <div className="flex items-center gap-3 mb-5">
          <div className="p-2 bg-gradient-to-r from-purple-500/20 to-blue-500/20 rounded-lg">
            <Globe className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">{t('settings.regionTitle')}</h3>
            <p className="text-xs text-gray-400 mt-0.5">{t('settings.regionDescription')}</p>
          </div>
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1.5">{t('settings.language')}</label>
            <LanguageSwitcher />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1.5">{t('settings.currency')}</label>
            <select
              value={currency}
              onChange={(e) => updateCurrencyMutation.mutate(e.target.value)}
              disabled={updateCurrencyMutation.isPending}
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
            >
              {currencyCodes().map((c: string) => (
                <option key={c} value={c} className="bg-gray-900">{c} ({currencySymbol(c)})</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1.5">{t('settings.country')}</label>
            <select
              value={user?.country ?? ''}
              onChange={(e) => updateCountryMutation.mutate(e.target.value)}
              disabled={updateCountryMutation.isPending}
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
            >
              <option value="" className="bg-gray-900">{t('settings.countryNotSet')}</option>
              {countryOptions.map((country) => (
                <option key={country.code} value={country.code} className="bg-gray-900">
                  {country.name}
                </option>
              ))}
            </select>
            <p className="mt-1.5 text-[11px] text-gray-500">{t('settings.countryHint')}</p>
          </div>
        </div>
      </section>

      {/* Учётная запись и безопасность */}
      <div className="order-1 grid grid-cols-1">
        {/* Профиль */}
        <section className="p-5 md:p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-gradient-to-r from-purple-500/20 to-blue-500/20 rounded-lg">
            <UserIcon className="w-5 h-5 text-purple-400" />
          </div>
          <h3 className="text-lg font-bold text-white">{t('settings.profile')}</h3>
        </div>
        
        <div className="divide-y divide-white/10 overflow-hidden rounded-xl border border-white/10 bg-white/[0.035]">
          <div className="p-4">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-300">
                  <UserIcon className="h-4 w-4 text-fuchsia-400" />
                  {t('settings.fullName')}
                </div>
                <p className="mt-1 truncate text-sm text-white">
                  {user.full_name || t('settings.notSpecified')}
                </p>
              </div>
              {!isFullNameEditing && (
                <button
                  type="button"
                  onClick={() => {
                    setFullNameForm(user.full_name ?? '');
                    setFullNameError(null);
                    setFullNameSuccess(false);
                    setIsFullNameEditing(true);
                  }}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-gray-300 transition hover:bg-white/10 hover:text-white"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  {t('settings.edit')}
                </button>
              )}
            </div>

            {isFullNameEditing && (
              <form onSubmit={handleFullNameSubmit} className="mt-4 space-y-3">
                <input
                  type="text"
                  value={fullNameForm}
                  onChange={(e) => setFullNameForm(e.target.value)}
                  maxLength={255}
                  autoFocus
                  className="w-full rounded-lg border border-white/20 bg-white/10 px-3 py-2 text-sm text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder={t('settings.fullNamePlaceholder')}
                />
                <p className="text-xs text-gray-400">{t('settings.fullNameHint')}</p>
                {fullNameError && (
                  <div className="flex items-center gap-2 text-xs text-red-400">
                    <XCircle className="h-3 w-3" />
                    <span>{fullNameError}</span>
                  </div>
                )}
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setFullNameForm(user.full_name ?? '');
                      setFullNameError(null);
                      setIsFullNameEditing(false);
                    }}
                    className="rounded-lg px-3 py-2 text-xs font-medium text-gray-400 transition hover:bg-white/5 hover:text-white"
                  >
                    {t('common.cancel')}
                  </button>
                  <button
                    type="submit"
                    disabled={updateFullNameMutation.isPending}
                    className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-3 py-2 text-xs font-medium text-white transition hover:bg-purple-500 disabled:opacity-50"
                  >
                    {updateFullNameMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                    {t('settings.save')}
                  </button>
                </div>
              </form>
            )}
            {fullNameSuccess && !isFullNameEditing && (
              <div className="mt-2 flex items-center gap-2 text-xs text-green-400">
                <CheckCircle className="h-3 w-3" />
                <span>{t('settings.success')}</span>
              </div>
            )}
          </div>

          <div className="p-4">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-300">
                  <UserIcon className="h-4 w-4 text-purple-400" />
                  {t('settings.username')}
                </div>
                <p className="mt-1 truncate text-sm text-white">{user.username}</p>
              </div>
              {!isUsernameEditing && (
                <button
                  type="button"
                  onClick={() => {
                    setUsernameForm({ new_username: user.username });
                    setUsernameError(null);
                    setUsernameSuccess(false);
                    setIsUsernameEditing(true);
                  }}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-gray-300 transition hover:bg-white/10 hover:text-white"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  {t('settings.edit')}
                </button>
              )}
            </div>

            {isUsernameEditing && (
              <form onSubmit={handleUsernameSubmit} className="mt-4 space-y-3">
                <input
                  type="text"
                  value={usernameForm.new_username}
                  onChange={(e) => setUsernameForm({ new_username: e.target.value })}
                  required
                  minLength={3}
                  autoFocus
                  className="w-full rounded-lg border border-white/20 bg-white/10 px-3 py-2 text-sm text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder={t('settings.newUsernamePlaceholder')}
                />
                {usernameError && (
                  <div className="flex items-center gap-2 text-xs text-red-400">
                    <XCircle className="h-3 w-3" />
                    <span>{usernameError}</span>
                  </div>
                )}
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setUsernameForm({ new_username: user.username });
                      setUsernameError(null);
                      setIsUsernameEditing(false);
                    }}
                    className="rounded-lg px-3 py-2 text-xs font-medium text-gray-400 transition hover:bg-white/5 hover:text-white"
                  >
                    {t('common.cancel')}
                  </button>
                  <button
                    type="submit"
                    disabled={updateUsernameMutation.isPending}
                    className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-3 py-2 text-xs font-medium text-white transition hover:bg-purple-500 disabled:opacity-50"
                  >
                    {updateUsernameMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                    {t('settings.save')}
                  </button>
                </div>
              </form>
            )}
            {usernameSuccess && !isUsernameEditing && (
              <div className="mt-2 flex items-center gap-2 text-xs text-green-400">
                <CheckCircle className="h-3 w-3" />
                <span>{t('settings.success')}</span>
              </div>
            )}
          </div>

          <div className="p-4">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-300">
                  <Mail className="h-4 w-4 text-blue-400" />
                  {t('settings.email')}
                </div>
                <p className="mt-1 truncate text-sm text-white">{user.email}</p>
              </div>
              {!isEmailEditing && (
                <button
                  type="button"
                  onClick={() => {
                    setEmailForm({ new_email: user.email });
                    setEmailError(null);
                    setEmailSuccess(false);
                    setIsEmailEditing(true);
                  }}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-gray-300 transition hover:bg-white/10 hover:text-white"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  {t('settings.edit')}
                </button>
              )}
            </div>

            {isEmailEditing && (
              <form onSubmit={handleEmailSubmit} className="mt-4 space-y-3">
                <input
                  type="email"
                  value={emailForm.new_email}
                  onChange={(e) => setEmailForm({ new_email: e.target.value })}
                  required
                  autoFocus
                  className="w-full rounded-lg border border-white/20 bg-white/10 px-3 py-2 text-sm text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder={t('settings.newEmailPlaceholder')}
                />
                <p className="text-xs text-blue-300/80">{t('settings.emailConfirmationHint')}</p>
                {emailError && (
                  <div className="flex items-center gap-2 text-xs text-red-400">
                    <XCircle className="h-3 w-3" />
                    <span>{emailError}</span>
                  </div>
                )}
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setEmailForm({ new_email: user.email });
                      setEmailError(null);
                      setIsEmailEditing(false);
                    }}
                    className="rounded-lg px-3 py-2 text-xs font-medium text-gray-400 transition hover:bg-white/5 hover:text-white"
                  >
                    {t('common.cancel')}
                  </button>
                  <button
                    type="submit"
                    disabled={updateEmailMutation.isPending}
                    className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-3 py-2 text-xs font-medium text-white transition hover:bg-purple-500 disabled:opacity-50"
                  >
                    {updateEmailMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                    {t('settings.save')}
                  </button>
                </div>
              </form>
            )}
            {emailSuccess && !isEmailEditing && (
              <div className="mt-2 flex items-center gap-2 text-xs text-green-400">
                <CheckCircle className="h-3 w-3" />
                <span>{t('settings.emailConfirmationSent')}</span>
              </div>
            )}
          </div>

          <div className="p-4">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-300">
                  <Lock className="h-4 w-4 text-pink-400" />
                  {t('settings.password')}
                </div>
                <p className="mt-1 text-sm text-white">
                  {user.has_password ? t('settings.passwordConfigured') : t('settings.passwordNotConfigured')}
                </p>
                <p className="mt-1 text-xs text-gray-400">{t('settings.passwordHint')}</p>
              </div>
              {!isPasswordEditing && (
                <button
                  type="button"
                  onClick={() => {
                    setPasswordForm({ current_password: '', new_password: '', confirm_password: '' });
                    setPasswordError(null);
                    setPasswordSuccess(false);
                    setIsPasswordEditing(true);
                  }}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-gray-300 transition hover:bg-white/10 hover:text-white"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  {user.has_password ? t('settings.edit') : t('settings.setPassword')}
                </button>
              )}
            </div>

          {isPasswordEditing && (
          <form onSubmit={handlePasswordSubmit} className="mt-4 space-y-3 border-t border-white/10 pt-4">
            {user.has_password && (
            <div>
              <label className="block text-gray-300 mb-1.5 text-xs font-medium">{t('settings.currentPassword')}</label>
              <div className="relative">
                <input
                  type={showPasswords.current ? "text" : "password"}
                  value={passwordForm.current_password}
                  onChange={(e) => setPasswordForm({ ...passwordForm, current_password: e.target.value })}
                  required
                  className="w-full px-3 py-2 pr-10 bg-white/10 border border-white/20 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder={t('settings.currentPasswordPlaceholder')}
                />
                <button
                  type="button"
                  onClick={() => setShowPasswords({ ...showPasswords, current: !showPasswords.current })}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-300 transition-colors"
                >
                  {showPasswords.current ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>
            )}

            <div>
              <label className="block text-gray-300 mb-1.5 text-xs font-medium">{t('settings.newPassword')}</label>
              <div className="relative">
                <input
                  type={showPasswords.new ? "text" : "password"}
                  value={passwordForm.new_password}
                  onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })}
                  required
                  minLength={8}
                  className="w-full px-3 py-2 pr-10 bg-white/10 border border-white/20 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder={t('settings.minCharsPlaceholder')}
                />
                <button
                  type="button"
                  onClick={() => setShowPasswords({ ...showPasswords, new: !showPasswords.new })}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-300 transition-colors"
                >
                  {showPasswords.new ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-gray-300 mb-1.5 text-xs font-medium">{t('settings.confirmPassword')}</label>
              <div className="relative">
                <input
                  type={showPasswords.confirm ? "text" : "password"}
                  value={passwordForm.confirm_password}
                  onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })}
                  required
                  minLength={8}
                  className="w-full px-3 py-2 pr-10 bg-white/10 border border-white/20 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder={t('settings.repeatPasswordPlaceholder')}
                />
                <button
                  type="button"
                  onClick={() => setShowPasswords({ ...showPasswords, confirm: !showPasswords.confirm })}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-300 transition-colors"
                >
                  {showPasswords.confirm ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            {passwordError && (
              <div className="flex items-center gap-2 text-red-400 text-xs">
                <XCircle className="w-3 h-3" />
                <span>{passwordError}</span>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setPasswordForm({ current_password: '', new_password: '', confirm_password: '' });
                  setPasswordError(null);
                  setIsPasswordEditing(false);
                }}
                className="rounded-lg px-3 py-2 text-xs font-medium text-gray-400 transition hover:bg-white/5 hover:text-white"
              >
                {t('common.cancel')}
              </button>
              <button
                type="submit"
                disabled={updatePasswordMutation.isPending}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-xs font-medium text-white transition hover:bg-purple-500 disabled:opacity-50"
              >
                {updatePasswordMutation.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="h-3.5 w-3.5" />
                )}
                <span>{user.has_password ? t('settings.changePassword') : t('settings.setPassword')}</span>
              </button>
            </div>
          </form>
          )}
          {passwordSuccess && !isPasswordEditing && (
            <div className="mt-3 flex items-center gap-2 text-xs text-green-400">
              <CheckCircle className="h-3 w-3" />
              <span>{t('settings.success')}</span>
            </div>
          )}
          </div>
        </div>
        </section>
      </div>

      {/* Настройки синхронизации - компактный вид */}
      <section className="order-3 border-t border-white/10 p-5 md:p-6 lg:col-span-2">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-500/20 rounded-lg">
              <Settings className="w-5 h-5 text-purple-300" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">{t('settings.syncTitle')}</h3>
              <p className="text-xs text-gray-400 mt-0.5">
                {t('settings.syncDescription')}
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {SYNC_CONTOURS.map((contour) => (
            <div key={contour.id} className="min-w-0 bg-white/5 rounded-xl p-4 border border-white/10">
              <h4 className="mb-1 text-sm font-semibold text-white">{t(contour.titleKey)}</h4>
              <p className="mb-3 text-xs text-gray-400">{t(contour.hintKey)}</p>
              <div className="space-y-2">
                {contour.directions.map((direction) => {
                  const enabled = direction.keys.some((key) => syncSettings[key]);
                  return (
                    <label
                      key={direction.labelKey}
                      className={`flex items-start justify-between gap-3 ${
                        direction.available ? 'cursor-pointer' : 'cursor-default'
                      }`}
                      title={direction.available ? undefined : t('settings.syncNotYet')}
                    >
                      <span className="min-w-0">
                        <span className={`text-sm ${direction.available ? 'text-gray-300' : 'text-gray-500'}`}>
                          {t(direction.labelKey)}
                          {!direction.available && (
                            <span className="ml-1.5 text-[11px] text-gray-500">
                              {t('settings.syncNotYet')}
                            </span>
                          )}
                        </span>
                        {direction.noteKey && (
                          <span className="block text-xs text-gray-500 mt-0.5">
                            {t(direction.noteKey)}
                          </span>
                        )}
                      </span>
                      <div className="relative flex-shrink-0">
                        <input
                          type="checkbox"
                          checked={direction.available && enabled}
                          disabled={!direction.available}
                          onChange={(e) => {
                            for (const key of direction.keys) {
                              handleSyncSettingsChange(key, e.target.checked);
                            }
                          }}
                          className="sr-only"
                        />
                        <div
                          className={`w-11 h-6 rounded-full transition-colors duration-200 flex items-center px-0.5 ${
                            direction.available && enabled
                              ? 'bg-purple-600 justify-end'
                              : 'bg-gray-600 justify-start'
                          } ${direction.available ? '' : 'opacity-50'}`}
                        >
                          <div className="w-5 h-5 bg-white rounded-full shadow-md" />
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <label className="mt-4 flex items-start justify-between gap-4 bg-white/5 rounded-xl p-4 border border-white/10 cursor-pointer group">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-white">{t('settings.syncPrinterEndpoints')}</div>
            <p className="text-xs text-gray-400 mt-0.5">{t('settings.syncPrinterEndpointsHint')}</p>
          </div>
          <div className="relative flex-shrink-0 mt-0.5">
            <input
              type="checkbox"
              checked={syncSettings.sync_printer_endpoints}
              onChange={(e) => handleSyncSettingsChange('sync_printer_endpoints', e.target.checked)}
              className="sr-only"
            />
            <div
              className={`w-11 h-6 rounded-full transition-colors duration-200 flex items-center px-0.5 ${
                syncSettings.sync_printer_endpoints ? 'bg-purple-600 justify-end' : 'bg-gray-600 justify-start'
              }`}
            >
              <div className="w-5 h-5 bg-white rounded-full shadow-md" />
            </div>
          </div>
        </label>

        {/* Кнопка сохранения */}
        <div className="flex justify-end mt-4">
          <button
            onClick={handleSaveSyncSettings}
            disabled={updateSettingsMutation.isPending}
            className="flex items-center gap-2 px-5 py-2.5 bg-purple-600 hover:bg-purple-500 text-white text-sm rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {updateSettingsMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{t('settings.saving')}</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span>{t('settings.save')}</span>
              </>
            )}
          </button>
        </div>
      </section>
      </div>

      {/* Опасная зона */}
      <section className="rounded-2xl border border-red-500/15 bg-red-500/[0.04] p-5 md:p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-red-500/20 rounded-lg">
            <AlertTriangle className="w-5 h-5 text-red-400" />
          </div>
          <h3 className="text-lg font-bold text-red-300">{t('settings.dangerZone')}</h3>
        </div>

        <p className="text-sm text-gray-400 mb-4">
          {t('settings.deleteAccountWarning')}
        </p>

        <button
          onClick={() => setShowDeleteModal(true)}
          className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-red-600 to-red-700 hover:from-red-700 hover:to-red-800 text-white text-sm rounded-lg transition-all shadow-lg shadow-red-500/25 hover:shadow-red-500/40"
        >
          <Trash2 className="w-4 h-4" />
          <span>{t('settings.deleteAccountButton')}</span>
        </button>
      </section>

      <DeleteAccountModal isOpen={showDeleteModal} onClose={() => setShowDeleteModal(false)} />
    </div>
  );
};
