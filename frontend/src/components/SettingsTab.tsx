/** Компонент вкладки настроек пользователя */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Settings, Lock, Mail, Save, CheckCircle, XCircle, Loader2, User as UserIcon, Eye, EyeOff } from 'lucide-react';
import { authAPI } from '../api/client';
import type { User } from '../types/api';
import { useAuth } from '../contexts/AuthContext';

interface SettingsTabProps {
  user: User;
  onUserUpdate: () => void;
}

export const SettingsTab: React.FC<SettingsTabProps> = ({ user, onUserUpdate }) => {
  const queryClient = useQueryClient();
  const { refreshUser } = useAuth();

  // Состояния для настроек синхронизации
  const [syncSettings, setSyncSettings] = useState({
    allow_printer_profiles_import: user.allow_printer_profiles_import ?? true,
    allow_printer_profiles_export: user.allow_printer_profiles_export ?? true,
    allow_print_profiles_import: user.allow_print_profiles_import ?? true,
    allow_print_profiles_export: user.allow_print_profiles_export ?? true,
  });

  // Состояния для формы изменения username
  const [usernameForm, setUsernameForm] = useState({
    new_username: user.username,
  });
  const [usernameError, setUsernameError] = useState<string | null>(null);
  const [usernameSuccess, setUsernameSuccess] = useState(false);

  // Состояния для формы изменения пароля
  const [passwordForm, setPasswordForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  });
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState(false);
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
      setUsernameForm({ new_username: user.username });
      setUsernameError(null);
      refreshUser();
      queryClient.invalidateQueries({ queryKey: ['user'] });
      setTimeout(() => setUsernameSuccess(false), 3000);
    },
    onError: (error: any) => {
      setUsernameError(error.response?.data?.detail || 'Ошибка при изменении username');
      setUsernameSuccess(false);
    },
  });

  // Мутация для изменения пароля
  const updatePasswordMutation = useMutation({
    mutationFn: authAPI.updatePassword,
    onSuccess: () => {
      setPasswordSuccess(true);
      setPasswordForm({ current_password: '', new_password: '', confirm_password: '' });
      setPasswordError(null);
      setTimeout(() => setPasswordSuccess(false), 3000);
    },
    onError: (error: any) => {
      setPasswordError(error.response?.data?.detail || 'Ошибка при изменении пароля');
      setPasswordSuccess(false);
    },
  });

  // Мутация для изменения email
  const updateEmailMutation = useMutation({
    mutationFn: authAPI.updateEmail,
    onSuccess: () => {
      setEmailSuccess(true);
      setEmailForm({ new_email: user.email });
      setEmailError(null);
      refreshUser();
      queryClient.invalidateQueries({ queryKey: ['user'] });
      setTimeout(() => setEmailSuccess(false), 3000);
    },
    onError: (error: any) => {
      setEmailError(error.response?.data?.detail || 'Ошибка при изменении email');
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
      setUsernameError('Username должен содержать минимум 3 символа');
      return;
    }

    if (usernameForm.new_username === user.username) {
      setUsernameError('Новый username должен отличаться от текущего');
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

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError(null);
    setPasswordSuccess(false);

    // Валидация
    if (passwordForm.new_password.length < 8) {
      setPasswordError('Пароль должен содержать минимум 8 символов');
      return;
    }

    if (passwordForm.new_password !== passwordForm.confirm_password) {
      setPasswordError('Пароли не совпадают');
      return;
    }

    if (passwordForm.current_password === passwordForm.new_password) {
      setPasswordError('Новый пароль должен отличаться от текущего');
      return;
    }

    try {
      await updatePasswordMutation.mutateAsync({
        current_password: passwordForm.current_password,
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
      setEmailError('Введите корректный email');
      return;
    }

    if (emailForm.new_email === user.email) {
      setEmailError('Новый email должен отличаться от текущего');
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

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Все настройки в одну строку */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1.5fr_2.5fr] gap-6">
        {/* Профиль (Username и Email) */}
        <section className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-6 shadow-xl">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-gradient-to-r from-purple-500/20 to-blue-500/20 rounded-lg">
            <UserIcon className="w-5 h-5 text-purple-400" />
          </div>
          <h3 className="text-xl font-bold text-white">Профиль</h3>
        </div>
        
        <div className="space-y-4">
          {/* Username */}
          <form onSubmit={handleUsernameSubmit} className="space-y-3">
            <div className="flex items-start gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <UserIcon className="w-4 h-4 text-purple-400" />
                  <label className="text-sm font-medium text-gray-300">Username</label>
                  <span className="text-xs text-gray-500">({user.username})</span>
                </div>
                <input
                  type="text"
                  value={usernameForm.new_username}
                  onChange={(e) => setUsernameForm({ new_username: e.target.value })}
                  required
                  minLength={3}
                  className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="Новый username"
                />
              </div>
              <button
                type="submit"
                disabled={updateUsernameMutation.isPending}
                className="h-[38px] px-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white text-sm rounded-lg transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap mt-7 flex items-center justify-center"
              >
                {updateUsernameMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Save className="w-4 h-4" />
                )}
              </button>
            </div>
            {usernameError && (
              <div className="flex items-center gap-2 text-red-400 text-xs">
                <XCircle className="w-3 h-3" />
                <span>{usernameError}</span>
              </div>
            )}
            {usernameSuccess && (
              <div className="flex items-center gap-2 text-green-400 text-xs">
                <CheckCircle className="w-3 h-3" />
                <span>Успешно!</span>
              </div>
            )}
          </form>

          {/* Email */}
          <form onSubmit={handleEmailSubmit} className="space-y-3">
            <div className="flex items-start gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <Mail className="w-4 h-4 text-blue-400" />
                  <label className="text-sm font-medium text-gray-300">Email</label>
                  <span className="text-xs text-gray-500">({user.email})</span>
                </div>
                <input
                  type="email"
                  value={emailForm.new_email}
                  onChange={(e) => setEmailForm({ new_email: e.target.value })}
                  required
                  className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="Новый email"
                />
                <p className="text-xs text-blue-300/80 mt-1">
                  На новый email будет отправлен код подтверждения
                </p>
              </div>
              <button
                type="submit"
                disabled={updateEmailMutation.isPending}
                className="h-[38px] px-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white text-sm rounded-lg transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap mt-7 flex items-center justify-center"
              >
                {updateEmailMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Save className="w-4 h-4" />
                )}
              </button>
            </div>
            {emailError && (
              <div className="flex items-center gap-2 text-red-400 text-xs">
                <XCircle className="w-3 h-3" />
                <span>{emailError}</span>
              </div>
            )}
            {emailSuccess && (
              <div className="flex items-center gap-2 text-green-400 text-xs">
                <CheckCircle className="w-3 h-3" />
                <span>Код подтверждения отправлен на новый email</span>
              </div>
            )}
          </form>
        </div>
      </section>

      {/* Изменение Пароля */}
      <section className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-6 shadow-xl">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-pink-500/20 rounded-lg">
              <Lock className="w-5 h-5 text-pink-400" />
            </div>
            <h3 className="text-lg font-bold text-white">Пароль</h3>
          </div>

          <form onSubmit={handlePasswordSubmit} className="space-y-3">
            <div>
              <label className="block text-gray-300 mb-1.5 text-xs font-medium">Текущий пароль</label>
              <div className="relative">
                <input
                  type={showPasswords.current ? "text" : "password"}
                  value={passwordForm.current_password}
                  onChange={(e) => setPasswordForm({ ...passwordForm, current_password: e.target.value })}
                  required
                  className="w-full px-3 py-2 pr-10 bg-white/10 border border-white/20 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="Введите текущий"
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

            <div>
              <label className="block text-gray-300 mb-1.5 text-xs font-medium">Новый пароль</label>
              <div className="relative">
                <input
                  type={showPasswords.new ? "text" : "password"}
                  value={passwordForm.new_password}
                  onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })}
                  required
                  minLength={8}
                  className="w-full px-3 py-2 pr-10 bg-white/10 border border-white/20 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="Минимум 8 символов"
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
              <label className="block text-gray-300 mb-1.5 text-xs font-medium">Подтвердите</label>
              <div className="relative">
                <input
                  type={showPasswords.confirm ? "text" : "password"}
                  value={passwordForm.confirm_password}
                  onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })}
                  required
                  minLength={8}
                  className="w-full px-3 py-2 pr-10 bg-white/10 border border-white/20 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="Повторите пароль"
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

            {passwordSuccess && (
              <div className="flex items-center gap-2 text-green-400 text-xs">
                <CheckCircle className="w-3 h-3" />
                <span>Успешно!</span>
              </div>
            )}

            <button
              type="submit"
              disabled={updatePasswordMutation.isPending}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white text-sm rounded-lg transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {updatePasswordMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Изменение...</span>
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  <span>Изменить</span>
                </>
              )}
            </button>
          </form>
        </section>

      {/* Настройки синхронизации - компактный вид */}
      <section className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-6 shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-500/20 rounded-lg">
              <Settings className="w-5 h-5 text-green-400" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">Синхронизация с OrcaSlicer</h3>
              <p className="text-xs text-gray-400 mt-0.5">
                Управление импортом и экспортом профилей принтеров и печати
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Профили принтеров */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2 min-h-[24px]">
              <span className="w-2 h-2 bg-purple-500 rounded-full flex-shrink-0"></span>
              <span className="whitespace-nowrap">Профили принтеров</span>
            </h4>
            <div className="space-y-2">
              <label className="flex items-center justify-between cursor-pointer group">
                <span className="text-sm text-gray-300 w-16">Импорт</span>
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={syncSettings.allow_printer_profiles_import}
                    onChange={(e) => handleSyncSettingsChange('allow_printer_profiles_import', e.target.checked)}
                    className="sr-only"
                  />
                  <div
                    className={`w-11 h-6 rounded-full transition-colors duration-200 flex items-center px-0.5 ${
                      syncSettings.allow_printer_profiles_import ? 'bg-purple-600 justify-end' : 'bg-gray-600 justify-start'
                    }`}
                  >
                    <div className="w-5 h-5 bg-white rounded-full shadow-md" />
                  </div>
                </div>
              </label>

              <label className="flex items-center justify-between cursor-pointer group">
                <span className="text-sm text-gray-300 w-16">Экспорт</span>
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={syncSettings.allow_printer_profiles_export}
                    onChange={(e) => handleSyncSettingsChange('allow_printer_profiles_export', e.target.checked)}
                    className="sr-only"
                  />
                  <div
                    className={`w-11 h-6 rounded-full transition-colors duration-200 flex items-center px-0.5 ${
                      syncSettings.allow_printer_profiles_export ? 'bg-purple-600 justify-end' : 'bg-gray-600 justify-start'
                    }`}
                  >
                    <div className="w-5 h-5 bg-white rounded-full shadow-md" />
                  </div>
                </div>
              </label>
            </div>
          </div>

          {/* Профили печати */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2 min-h-[24px]">
              <span className="w-2 h-2 bg-pink-500 rounded-full flex-shrink-0"></span>
              <span className="whitespace-nowrap">Профили печати</span>
            </h4>
            <div className="space-y-2">
              <label className="flex items-center justify-between cursor-pointer group">
                <span className="text-sm text-gray-300 w-16">Импорт</span>
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={syncSettings.allow_print_profiles_import}
                    onChange={(e) => handleSyncSettingsChange('allow_print_profiles_import', e.target.checked)}
                    className="sr-only"
                  />
                  <div
                    className={`w-11 h-6 rounded-full transition-colors duration-200 flex items-center px-0.5 ${
                      syncSettings.allow_print_profiles_import ? 'bg-purple-600 justify-end' : 'bg-gray-600 justify-start'
                    }`}
                  >
                    <div className="w-5 h-5 bg-white rounded-full shadow-md" />
                  </div>
                </div>
              </label>

              <label className="flex items-center justify-between cursor-pointer group">
                <span className="text-sm text-gray-300 w-16">Экспорт</span>
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={syncSettings.allow_print_profiles_export}
                    onChange={(e) => handleSyncSettingsChange('allow_print_profiles_export', e.target.checked)}
                    className="sr-only"
                  />
                  <div
                    className={`w-11 h-6 rounded-full transition-colors duration-200 flex items-center px-0.5 ${
                      syncSettings.allow_print_profiles_export ? 'bg-purple-600 justify-end' : 'bg-gray-600 justify-start'
                    }`}
                  >
                    <div className="w-5 h-5 bg-white rounded-full shadow-md" />
                  </div>
                </div>
              </label>
            </div>
          </div>
        </div>

        {/* Кнопка сохранения */}
        <div className="flex justify-end mt-4">
          <button
            onClick={handleSaveSyncSettings}
            disabled={updateSettingsMutation.isPending}
            className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white text-sm rounded-lg transition-all shadow-lg shadow-green-500/25 hover:shadow-green-500/40 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {updateSettingsMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Сохранение...</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span>Сохранить</span>
              </>
            )}
          </button>
        </div>
      </section>
      </div>
    </div>
  );
};
