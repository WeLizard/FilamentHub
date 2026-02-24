/** Модальное окно установки нового пароля */

import { useState, FormEvent, useEffect } from 'react';
import { Lock, X, CheckCircle, AlertCircle, Loader, Eye, EyeOff } from 'lucide-react';
import { authAPI } from '../api/client';
import { useNavigate } from 'react-router-dom';
import { useHeaderVisible } from '../hooks/useHeaderVisible';
import { useTranslation } from 'react-i18next';
import { translateApiError } from '../utils/translateApiError';

interface ResetPasswordModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string;
}

export const ResetPasswordModal: React.FC<ResetPasswordModalProps> = ({
  isOpen,
  onClose,
  token,
}) => {
  const { t } = useTranslation();
  const isHeaderVisible = useHeaderVisible();
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const navigate = useNavigate();

  // Проверка сложности пароля
  const getPasswordStrength = (pwd: string): { strength: number; label: string; color: string } => {
    if (!pwd) return { strength: 0, label: '', color: '' };
    
    let strength = 0;
    if (pwd.length >= 8) strength++;
    if (pwd.length >= 12) strength++;
    if (/[a-z]/.test(pwd)) strength++;
    if (/[A-Z]/.test(pwd)) strength++;
    if (/[0-9]/.test(pwd)) strength++;
    if (/[^a-zA-Z0-9]/.test(pwd)) strength++;

    if (strength <= 2) return { strength, label: t('authModal.password_strength_weak'), color: 'text-red-400' };
    if (strength <= 4) return { strength, label: t('authModal.password_strength_medium'), color: 'text-yellow-400' };
    return { strength, label: t('authModal.password_strength_strong'), color: 'text-green-400' };
  };

  const passwordStrength = getPasswordStrength(newPassword);

  useEffect(() => {
    if (!isOpen) {
      setNewPassword('');
      setConfirmPassword('');
      setError(null);
      setIsSuccess(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    // Валидация
    if (newPassword !== confirmPassword) {
      setError(t('authModal.error_passwords_mismatch'));
      return;
    }

    if (newPassword.length < 8) {
      setError(t('authModal.error_password_too_short'));
      return;
    }

    if (!/[a-zA-Zа-яА-ЯёЁ]/.test(newPassword)) {
      setError(t('authModal.error_password_no_letter'));
      return;
    }

    if (!/\d/.test(newPassword)) {
      setError(t('authModal.error_password_no_digit'));
      return;
    }

    setIsLoading(true);

    try {
      await authAPI.resetPassword(token, newPassword);
      setIsSuccess(true);
      
      // Через 2 секунды закрываем модалку и перенаправляем на страницу входа
      setTimeout(() => {
        handleClose();
        navigate('/');
      }, 2000);
    } catch (err: any) {
      let errorMessage = t('resetPasswordModal.error_reset_failed');

      if (err.response) {
        const status = err.response.status;
        const detail = err.response.data?.detail;

        if (status === 429) {
          errorMessage = t('forgotPasswordModal.error_too_many_requests');
        } else {
          errorMessage = translateApiError(t, detail, t('resetPasswordModal.error_reset_failed'));
        }
      } else if (err.request) {
        errorMessage = t('authModal.error_no_connection');
      }

      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    if (!isLoading && !isSuccess) {
      setNewPassword('');
      setConfirmPassword('');
      setError(null);
      setIsSuccess(false);
      onClose();
    }
  };

  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center p-4 ${isHeaderVisible ? 'pt-[88px]' : ''}`}>
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={handleClose}
      ></div>

      {/* Modal */}
      <div className="relative w-full max-w-md bg-white/10 backdrop-blur-sm rounded-2xl border border-white/20 shadow-xl z-10 overflow-hidden">
        {/* Header */}
        <div className="relative p-8 pb-0">
          <button
            onClick={handleClose}
            disabled={isLoading || isSuccess}
            className="absolute top-4 right-4 p-2 text-gray-400 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <X className="w-5 h-5" />
          </button>

          <div className="text-center mb-8">
            <div className="w-16 h-16 flex items-center justify-center mx-auto mb-4">
              <img src="/logo.svg" alt="FilamentHub Logo" className="w-16 h-16 object-contain" />
            </div>
            <h2 className="text-2xl font-bold text-white mb-2">{t('resetPasswordModal.title')}</h2>
            <p className="text-gray-300">{t('resetPasswordModal.subtitle')}</p>
          </div>
        </div>

        {/* Content */}
        <div className="px-8 pb-8">
          {isSuccess ? (
            <div className="text-center space-y-4">
              <div className="flex justify-center">
                <CheckCircle className="w-16 h-16 text-green-400" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-white mb-2">{t('resetPasswordModal.success_title')}</h3>
                <p className="text-gray-300">
                  {t('resetPasswordModal.success_message')}
                </p>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              <div className="space-y-4">
                {/* Error Message */}
                {error && (
                  <div className="p-3 bg-red-500/20 border border-red-500/30 rounded-xl text-red-300 text-sm flex items-start space-x-2">
                    <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                    <span>{error}</span>
                  </div>
                )}

                <div>
                  <label className="block text-gray-300 mb-2">{t('resetPasswordModal.label_new_password')}</label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      required
                      disabled={isLoading}
                      className="w-full pl-10 pr-12 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                      placeholder="••••••••"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
                    >
                      {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                  {/* Индикатор сложности пароля */}
                  {newPassword && (
                    <div className="mt-2">
                      <div className="flex items-center space-x-2 mb-1">
                        <div className="flex-1 h-1 bg-white/10 rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all ${
                              passwordStrength.strength <= 2
                                ? 'bg-red-500'
                                : passwordStrength.strength <= 4
                                  ? 'bg-yellow-500'
                                  : 'bg-green-500'
                            }`}
                            style={{ width: `${(passwordStrength.strength / 6) * 100}%` }}
                          ></div>
                        </div>
                        <span className={`text-xs font-medium ${passwordStrength.color}`}>
                          {passwordStrength.label}
                        </span>
                      </div>
                      <p className="text-xs text-gray-400">
                        {t('authModal.password_tip')}
                      </p>
                    </div>
                  )}
                </div>

                <div>
                  <label className="block text-gray-300 mb-2">{t('resetPasswordModal.label_confirm_password')}</label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                    <input
                      type={showConfirmPassword ? 'text' : 'password'}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      required
                      disabled={isLoading}
                      className={`w-full pl-10 pr-12 py-3 bg-white/10 border rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                        confirmPassword && newPassword !== confirmPassword
                          ? 'border-red-500/50'
                          : confirmPassword && newPassword === confirmPassword
                            ? 'border-green-500/50'
                            : 'border-white/20'
                      }`}
                      placeholder="••••••••"
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
                    >
                      {showConfirmPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                  {confirmPassword && newPassword !== confirmPassword && (
                    <p className="mt-1 text-xs text-red-400">{t('authModal.error_passwords_mismatch')}</p>
                  )}
                  {confirmPassword && newPassword === confirmPassword && (
                    <p className="mt-1 text-xs text-green-400">{t('authModal.passwords_match')}</p>
                  )}
                </div>

                <button
                  type="submit"
                  disabled={isLoading || !newPassword || !confirmPassword || newPassword !== confirmPassword}
                  className="w-full mt-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white py-3 px-6 rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
                >
                  {isLoading ? (
                    <>
                      <Loader className="w-5 h-5 animate-spin" />
                      <span>{t('resetPasswordModal.changing_password')}</span>
                    </>
                  ) : (
                    <span>{t('resetPasswordModal.change_password_button')}</span>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};

