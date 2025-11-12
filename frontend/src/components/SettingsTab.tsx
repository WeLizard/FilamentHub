/** Компонент вкладки настроек пользователя */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Settings, Lock, Mail, Save, CheckCircle, XCircle, Loader2, Info } from 'lucide-react';
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

  // Состояния для формы изменения пароля
  const [passwordForm, setPasswordForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  });
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  // Состояния для формы изменения email
  const [emailForm, setEmailForm] = useState({
    new_email: user.email,
    password: '',
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
      setEmailForm({ ...emailForm, password: '' });
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
        password: emailForm.password,
      });
    } catch (error) {
      // Ошибка обрабатывается в onError мутации
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Настройки синхронизации */}
      <section className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-6 shadow-xl">
        <div className="flex items-center gap-3 mb-6">
          <Settings className="w-6 h-6 text-purple-400" />
          <h3 className="text-2xl font-bold text-white">Настройки синхронизации с OrcaSlicer</h3>
        </div>
        <p className="text-gray-300 mb-6 text-sm">
          Управляйте разрешениями на импорт и экспорт профилей принтеров и печати при синхронизации с OrcaSlicer.
          В будущем эти настройки будут использоваться для управления полными бандлами (Филамент + Принтер + Печать).
        </p>

        <div className="space-y-4">
          {/* Профили принтеров */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <h4 className="text-lg font-semibold text-white mb-4">Профили принтеров</h4>
            <div className="space-y-3">
              <label className="flex items-center justify-between cursor-pointer group">
                <div className="flex-1">
                  <span className="text-white font-medium">Разрешить импорт профилей принтеров</span>
                  <p className="text-xs text-gray-400 mt-1">
                    Позволяет OrcaSlicer отправлять ваши профили принтеров в FilamentHub
                  </p>
                </div>
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={syncSettings.allow_printer_profiles_import}
                    onChange={(e) => handleSyncSettingsChange('allow_printer_profiles_import', e.target.checked)}
                    className="sr-only"
                  />
                  <div
                    className={`w-14 h-7 rounded-full transition-colors duration-200 ${
                      syncSettings.allow_printer_profiles_import
                        ? 'bg-purple-600'
                        : 'bg-gray-600'
                    }`}
                  >
                    <div
                      className={`w-6 h-6 bg-white rounded-full shadow-md transform transition-transform duration-200 ${
                        syncSettings.allow_printer_profiles_import
                          ? 'translate-x-7'
                          : 'translate-x-1'
                      }`}
                      style={{ marginTop: '2px' }}
                    />
                  </div>
                </div>
              </label>

              <label className="flex items-center justify-between cursor-pointer group">
                <div className="flex-1">
                  <span className="text-white font-medium">Разрешить экспорт профилей принтеров</span>
                  <p className="text-xs text-gray-400 mt-1">
                    Позволяет OrcaSlicer получать ваши профили принтеров из FilamentHub
                  </p>
                </div>
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={syncSettings.allow_printer_profiles_export}
                    onChange={(e) => handleSyncSettingsChange('allow_printer_profiles_export', e.target.checked)}
                    className="sr-only"
                  />
                  <div
                    className={`w-14 h-7 rounded-full transition-colors duration-200 ${
                      syncSettings.allow_printer_profiles_export
                        ? 'bg-purple-600'
                        : 'bg-gray-600'
                    }`}
                  >
                    <div
                      className={`w-6 h-6 bg-white rounded-full shadow-md transform transition-transform duration-200 ${
                        syncSettings.allow_printer_profiles_export
                          ? 'translate-x-7'
                          : 'translate-x-1'
                      }`}
                      style={{ marginTop: '2px' }}
                    />
                  </div>
                </div>
              </label>
            </div>
          </div>

          {/* Профили печати */}
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <h4 className="text-lg font-semibold text-white mb-4">Профили печати</h4>
            <div className="space-y-3">
              <label className="flex items-center justify-between cursor-pointer group">
                <div className="flex-1">
                  <span className="text-white font-medium">Разрешить импорт профилей печати</span>
                  <p className="text-xs text-gray-400 mt-1">
                    Позволяет OrcaSlicer отправлять ваши профили печати в FilamentHub
                  </p>
                </div>
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={syncSettings.allow_print_profiles_import}
                    onChange={(e) => handleSyncSettingsChange('allow_print_profiles_import', e.target.checked)}
                    className="sr-only"
                  />
                  <div
                    className={`w-14 h-7 rounded-full transition-colors duration-200 ${
                      syncSettings.allow_print_profiles_import
                        ? 'bg-purple-600'
                        : 'bg-gray-600'
                    }`}
                  >
                    <div
                      className={`w-6 h-6 bg-white rounded-full shadow-md transform transition-transform duration-200 ${
                        syncSettings.allow_print_profiles_import
                          ? 'translate-x-7'
                          : 'translate-x-1'
                      }`}
                      style={{ marginTop: '2px' }}
                    />
                  </div>
                </div>
              </label>

              <label className="flex items-center justify-between cursor-pointer group">
                <div className="flex-1">
                  <span className="text-white font-medium">Разрешить экспорт профилей печати</span>
                  <p className="text-xs text-gray-400 mt-1">
                    Позволяет OrcaSlicer получать ваши профили печати из FilamentHub
                  </p>
                </div>
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={syncSettings.allow_print_profiles_export}
                    onChange={(e) => handleSyncSettingsChange('allow_print_profiles_export', e.target.checked)}
                    className="sr-only"
                  />
                  <div
                    className={`w-14 h-7 rounded-full transition-colors duration-200 ${
                      syncSettings.allow_print_profiles_export
                        ? 'bg-purple-600'
                        : 'bg-gray-600'
                    }`}
                  >
                    <div
                      className={`w-6 h-6 bg-white rounded-full shadow-md transform transition-transform duration-200 ${
                        syncSettings.allow_print_profiles_export
                          ? 'translate-x-7'
                          : 'translate-x-1'
                      }`}
                      style={{ marginTop: '2px' }}
                    />
                  </div>
                </div>
              </label>
            </div>
          </div>

          {/* Кнопка сохранения */}
          <div className="flex justify-end pt-4">
            <button
              onClick={handleSaveSyncSettings}
              disabled={updateSettingsMutation.isPending}
              className="flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {updateSettingsMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Сохранение...</span>
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  <span>Сохранить настройки</span>
                </>
              )}
            </button>
          </div>
        </div>
      </section>

      {/* Изменение пароля */}
      <section className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-6 shadow-xl">
        <div className="flex items-center gap-3 mb-6">
          <Lock className="w-6 h-6 text-purple-400" />
          <h3 className="text-2xl font-bold text-white">Изменить пароль</h3>
        </div>

        <form onSubmit={handlePasswordSubmit} className="space-y-4">
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Текущий пароль</label>
            <input
              type="password"
              value={passwordForm.current_password}
              onChange={(e) => setPasswordForm({ ...passwordForm, current_password: e.target.value })}
              required
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="Введите текущий пароль"
            />
          </div>

          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Новый пароль</label>
            <input
              type="password"
              value={passwordForm.new_password}
              onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })}
              required
              minLength={8}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="Минимум 8 символов"
            />
          </div>

          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Подтвердите новый пароль</label>
            <input
              type="password"
              value={passwordForm.confirm_password}
              onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })}
              required
              minLength={8}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="Повторите новый пароль"
            />
          </div>

          {passwordError && (
            <div className="flex items-center gap-2 text-red-400 text-sm">
              <XCircle className="w-4 h-4" />
              <span>{passwordError}</span>
            </div>
          )}

          {passwordSuccess && (
            <div className="flex items-center gap-2 text-green-400 text-sm">
              <CheckCircle className="w-4 h-4" />
              <span>Пароль успешно изменён</span>
            </div>
          )}

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={updatePasswordMutation.isPending}
              className="flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {updatePasswordMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Изменение...</span>
                </>
              ) : (
                <>
                  <Lock className="w-4 h-4" />
                  <span>Изменить пароль</span>
                </>
              )}
            </button>
          </div>
        </form>
      </section>

      {/* Изменение email */}
      <section className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-6 shadow-xl">
        <div className="flex items-center gap-3 mb-6">
          <Mail className="w-6 h-6 text-purple-400" />
          <h3 className="text-2xl font-bold text-white">Изменить email</h3>
        </div>

        <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4 mb-6">
          <div className="flex items-start gap-3">
            <Info className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-blue-200">
              <p className="font-semibold mb-1">Важно:</p>
              <p>
                После изменения email вам потребуется повторно верифицировать новый адрес.
                На новый email будет отправлено письмо с подтверждением.
              </p>
            </div>
          </div>
        </div>

        <form onSubmit={handleEmailSubmit} className="space-y-4">
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Текущий email</label>
            <input
              type="email"
              value={user.email}
              disabled
              className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-gray-400 cursor-not-allowed"
            />
          </div>

          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Новый email</label>
            <input
              type="email"
              value={emailForm.new_email}
              onChange={(e) => setEmailForm({ ...emailForm, new_email: e.target.value })}
              required
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="example@domain.com"
            />
          </div>

          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Пароль для подтверждения</label>
            <input
              type="password"
              value={emailForm.password}
              onChange={(e) => setEmailForm({ ...emailForm, password: e.target.value })}
              required
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="Введите текущий пароль"
            />
          </div>

          {emailError && (
            <div className="flex items-center gap-2 text-red-400 text-sm">
              <XCircle className="w-4 h-4" />
              <span>{emailError}</span>
            </div>
          )}

          {emailSuccess && (
            <div className="flex items-center gap-2 text-green-400 text-sm">
              <CheckCircle className="w-4 h-4" />
              <span>Email успешно изменён. Проверьте почту для подтверждения.</span>
            </div>
          )}

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={updateEmailMutation.isPending}
              className="flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {updateEmailMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Изменение...</span>
                </>
              ) : (
                <>
                  <Mail className="w-4 h-4" />
                  <span>Изменить email</span>
                </>
              )}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
};

