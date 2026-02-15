/** Модальное окно авторизации */

import { useState, useEffect, FormEvent } from 'react';
import { Mail, Lock, LogIn, UserPlus, User, Factory, Package, X, Check, Eye, EyeOff, AlertCircle, KeyRound } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { Recaptcha } from './Captcha';
import { TermsModal } from './TermsModal';
import { ConsentModal } from './ConsentModal';
import { ForgotPasswordModal } from './ForgotPasswordModal';
import { useHeaderVisible } from '../hooks/useHeaderVisible';
import { useTranslation } from 'react-i18next';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialMode?: 'login' | 'register';
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onClose, initialMode = 'login' }) => {
  const { t } = useTranslation();
  const isHeaderVisible = useHeaderVisible();
  const [authMode, setAuthMode] = useState<'login' | 'register'>(initialMode);
  const [authMethod, setAuthMethod] = useState<'email' | 'google'>('email'); // Новое состояние для метода входа
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [username, setUsername] = useState('');
  const [agreed, setAgreed] = useState(false);
  const [recaptchaToken, setRecaptchaToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isTermsModalOpen, setIsTermsModalOpen] = useState(false);
  const [isConsentModalOpen, setIsConsentModalOpen] = useState(false);
  const [isForgotPasswordModalOpen, setIsForgotPasswordModalOpen] = useState(false);

  const { login, register } = useAuth();

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

  const passwordStrength = getPasswordStrength(password);

  // Очищаем ошибки при закрытии модального окна
  useEffect(() => {
    if (!isOpen) {
      setError(null);
      setIsLoading(false);
      setAuthMethod('email'); // Сбрасываем метод входа
      setRecaptchaToken(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      if (authMode === 'login') {
        await login(email, password);
        // Закрываем модалку только при успешном логине
        onClose();
        setEmail('');
        setPassword('');
        setIsLoading(false);
        setError(null); // Очищаем ошибки при успехе
      } else {
        // Валидация без очистки полей
        if (!agreed) {
          setError(t('authModal.error_agree_terms'));
          setIsLoading(false);
          return;
        }
        if (password !== confirmPassword) {
          setError(t('authModal.error_passwords_mismatch'));
          setIsLoading(false);
          return;
        }
        if (password.length < 8) {
          setError(t('authModal.error_password_too_short'));
          setIsLoading(false);
          return;
        }
        
        // Все проверки пройдены - регистрируем (с reCAPTCHA токеном если есть)
        await register({
          email,
          username,
          password,
          role: 'user',
          recaptcha_token: recaptchaToken ?? undefined,
        });
        
        // Успешная регистрация - закрываем модальное окно
        onClose();
        
        // Очищаем поля только после успешной регистрации
        setEmail('');
        setPassword('');
        setConfirmPassword('');
        setUsername('');
        setAgreed(false);
        setRecaptchaToken(null);
        setIsLoading(false);
      }
    } catch (err: any) {
      // Обработка различных типов ошибок
      let errorMessage = authMode === 'login' 
        ? t('authModal.error_login_failed')
        : t('authModal.error_register_failed');
      
      if (err.response) {
        // Ошибка от сервера
        const status = err.response.status;
        const detail = err.response.data?.detail;
        
        if (status === 400) {
          // Ошибка валидации или дубликат
          if (typeof detail === 'string') {
            // Переводим понятные сообщения на русский
            if (detail.toLowerCase().includes('already registered') || detail.toLowerCase().includes('email')) {
              errorMessage = t('authModal.error_email_registered');
            } else if (detail.toLowerCase().includes('username') || detail.toLowerCase().includes('taken')) {
              errorMessage = t('authModal.error_username_taken');
            } else if (detail.toLowerCase().includes('invalid role')) {
              errorMessage = t('authModal.error_invalid_role');
            } else {
              errorMessage = detail;
            }
          } else if (Array.isArray(detail)) {
            // Валидационные ошибки от Pydantic
            errorMessage = detail.map((item: any) => {
              const msg = item.msg || item.message || '';
              // Переводим типичные ошибки валидации
              if (msg.includes('email')) {
                return t('authModal.error_invalid_email');
              } else if (msg.includes('username') && msg.includes('length')) {
                return t('authModal.error_username_length');
              } else if (msg.includes('password') && msg.includes('length')) {
                return t('authModal.error_password_length');
              }
              return msg;
            }).join(' ');
          } else if (detail) {
            errorMessage = JSON.stringify(detail);
          }
        } else if (status === 401) {
          // Неверные учетные данные - показываем конкретное сообщение
          errorMessage = t('authModal.error_wrong_credentials');
          // Очищаем пароль для безопасности
          setPassword('');
          // Показываем капчу после нескольких неудачных попыток (опционально)
        } else if (status === 403) {
          errorMessage = t('authModal.error_account_locked');
        } else if (status === 500) {
          errorMessage = t('authModal.error_server_error');
        } else if (typeof detail === 'string') {
          errorMessage = detail;
        }
      } else if (err.request) {
        // Запрос отправлен, но ответа нет
        errorMessage = t('authModal.error_no_connection');
      } else if (err.message) {
        errorMessage = err.message;
      }
      
      setError(errorMessage);
      setIsLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    // ЗАГЛУШКА: TODO - Реализовать Google OAuth
    setError(t('authModal.google_login_soon'));
  };

  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center p-4 ${isHeaderVisible ? 'pt-[88px]' : ''}`}>
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={(e) => {
          // Закрываем модалку только если не идет загрузка и нет ошибки
          if (!isLoading && !error) {
            onClose();
          }
        }}
      ></div>

      {/* Modal */}
      <div className="relative w-full max-w-md max-h-[90vh] bg-white/10 backdrop-blur-sm rounded-xl sm:rounded-2xl border border-white/20 shadow-xl z-10 overflow-hidden flex flex-col mx-2 sm:mx-0">
        {/* Header */}
        <div className="relative p-4 sm:p-8 pb-0 flex-shrink-0">
          {/* Close Button */}
          <button
            onClick={(e) => {
              // Закрываем модалку только если не идет загрузка
              if (!isLoading) {
                onClose();
              }
            }}
            disabled={isLoading}
            className="absolute top-3 right-3 sm:top-4 sm:right-4 p-2 text-gray-400 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <X className="w-5 h-5" />
          </button>

          <div className="text-center mb-4 sm:mb-8">
            <div className="w-12 h-12 sm:w-16 sm:h-16 flex items-center justify-center mx-auto mb-3 sm:mb-4">
              <img src="/logo.svg" alt="FilamentHub Logo" className="w-12 h-12 sm:w-16 sm:h-16 object-contain" />
            </div>
            <h2 className="text-xl sm:text-2xl font-bold text-white mb-1 sm:mb-2">FilamentHub</h2>
            <p className="text-sm sm:text-base text-gray-300">{t('authModal.title')}</p>
          </div>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-8 pb-4 sm:pb-8">

        {/* Tabs */}
        <div className="flex mb-6">
          <button
            onClick={() => {
              setAuthMode('login');
              setAuthMethod('email'); // Сбрасываем метод входа на email
              setError(null);
              setRecaptchaToken(null);
            }}
            className={`flex-1 py-3 px-4 rounded-l-xl transition-all ${
              authMode === 'login'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            {t('authModal.tab_login')}
          </button>
          <button
            onClick={() => {
              setAuthMode('register');
              setAuthMethod('email'); // Регистрация всегда через email
              setError(null);
              setRecaptchaToken(null);
            }}
            className={`flex-1 py-3 px-4 rounded-r-xl transition-all ${
              authMode === 'register'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            {t('authModal.tab_register')}
          </button>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-4 p-3 bg-red-500/20 border border-red-500/30 rounded-xl text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Переключалка методов входа (только для входа) */}
        {authMode === 'login' && (
          <div className="mb-4">
            <div className="flex bg-white/5 rounded-xl p-1 border border-white/10">
              <button
                type="button"
                onClick={() => setAuthMethod('email')}
                className={`flex-1 py-2 px-4 rounded-lg transition-all text-sm font-medium ${
                  authMethod === 'email'
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-300 hover:text-white'
                }`}
              >
                {t('authModal.method_email')}
              </button>
              <button
                type="button"
                onClick={() => setAuthMethod('google')}
                className={`flex-1 py-2 px-4 rounded-lg transition-all text-sm font-medium ${
                  authMethod === 'google'
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-300 hover:text-white'
                }`}
              >
                {t('authModal.method_google')}
              </button>
            </div>
          </div>
        )}

        {/* ЗАГЛУШКА: Google Login Button - показываем только если выбран метод Google */}
        {authMode === 'login' && authMethod === 'google' && (
          <button
            type="button"
            onClick={handleGoogleLogin}
            disabled={isLoading}
            className="w-full mb-4 bg-white/10 hover:bg-white/20 text-white py-3 px-6 rounded-xl transition-all border border-white/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="currentColor"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="currentColor"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="currentColor"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            <span>{t('authModal.login_with_google')}</span>
          </button>
        )}

        {/* Форма Email - показываем только если выбран метод Email или это регистрация */}
        {(authMode === 'register' || (authMode === 'login' && authMethod === 'email')) && (
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label className="block text-gray-300 mb-2">
                {authMode === 'login' ? t('authModal.label_email_or_login') : t('authModal.label_email')}
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5 pointer-events-none" />
                <input
                  type={authMode === 'login' ? 'text' : 'email'}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full pl-10 pr-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                  placeholder={authMode === 'login' ? t('authModal.placeholder_email_or_login') : t('authModal.placeholder_email')}
                />
              </div>
              {authMode === 'register' && (
                <p className="mt-1 text-xs text-gray-400 flex items-start">
                  <AlertCircle className="w-3.5 h-3.5 text-yellow-400 mr-1.5 flex-shrink-0 mt-0.5" />
                  <span>{t('authModal.corporate_email_tip')}</span>
                </p>
              )}
            </div>

            {authMode === 'register' && (
              <div>
                <label className="block text-gray-300 mb-2">{t('authModal.label_username')}</label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    minLength={3}
                    maxLength={100}
                    className="w-full pl-10 pr-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                    placeholder={t('authModal.placeholder_username')}
                  />
                </div>
                {username && username.length < 3 && (
                  <p className="mt-1 text-xs text-red-400">{t('authModal.username_too_short')}</p>
                )}
                {username && username.length > 100 && (
                  <p className="mt-1 text-xs text-red-400">{t('authModal.username_too_long')}</p>
                )}
                {username && !/^[a-zA-Z0-9_-]+$/.test(username) && (
                  <p className="mt-1 text-xs text-red-400">{t('authModal.username_invalid_chars')}</p>
                )}
              </div>
            )}

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-gray-300">{t('authModal.label_password')}</label>
                {authMode === 'login' && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      setIsForgotPasswordModalOpen(true);
                    }}
                    className="text-sm text-purple-400 hover:text-purple-300 transition-colors flex items-center space-x-1"
                  >
                    <KeyRound className="w-3.5 h-3.5" />
                    <span>{t('authModal.forgot_password')}</span>
                  </button>
                )}
              </div>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full pl-10 pr-12 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                  placeholder={t('authModal.placeholder_password')}
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
              {authMode === 'register' && password && (
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

            {/* Поле подтверждения пароля (только для регистрации) */}
            {authMode === 'register' && (
              <div>
                <label className="block text-gray-300 mb-2">{t('authModal.label_confirm_password')}</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                  <input
                    type={showConfirmPassword ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    className={`w-full pl-10 pr-12 py-3 bg-white/10 border rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all ${
                      confirmPassword && password !== confirmPassword
                        ? 'border-red-500/50'
                        : confirmPassword && password === confirmPassword
                          ? 'border-green-500/50'
                          : 'border-white/20'
                    }`}
                    placeholder={t('authModal.placeholder_password')}
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
                  >
                    {showConfirmPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
                {confirmPassword && password !== confirmPassword && (
                  <p className="mt-1 text-xs text-red-400">{t('authModal.error_passwords_mismatch')}</p>
                )}
                {confirmPassword && password === confirmPassword && (
                  <p className="mt-1 text-xs text-green-400">{t('authModal.passwords_match')}</p>
                )}
              </div>
            )}

            {authMode === 'register' && (
              <>
                <div className="flex items-start space-x-2">
                  <button
                    type="button"
                    onClick={() => setAgreed(!agreed)}
                    className={`mt-1 w-5 h-5 flex items-center justify-center rounded ${
                      agreed
                        ? 'bg-purple-600 text-white'
                        : 'bg-white/10 border border-white/20 text-transparent'
                    } transition-all`}
                  >
                    {agreed && <Check className="w-4 h-4" />}
                  </button>
                  <label className="text-gray-300 text-sm cursor-pointer flex-1">
                    {t('authModal.agree_terms_1')}{' '}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setIsTermsModalOpen(true);
                      }}
                      className="text-purple-400 hover:text-purple-300 underline"
                    >
                      {t('authModal.agree_terms_user_agreement')}
                    </button>{' '}
                    {t('authModal.agree_terms_2')}{' '}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setIsConsentModalOpen(true);
                      }}
                      className="text-purple-400 hover:text-purple-300 underline"
                    >
                      {t('authModal.agree_terms_personal_data')}
                    </button>
                  </label>
                </div>

                {/* reCAPTCHA v3 — невидимая, запускается автоматически */}
                <Recaptcha onToken={setRecaptchaToken} action="register" />
              </>
            )}

            <button
              type="submit"
              disabled={isLoading || (authMode === 'register' && !agreed)}
              className="w-full mt-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white py-3 px-6 rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                t('authModal.loading')
              ) : (
                <>
                  {authMode === 'login' ? (
                    <>
                      <LogIn className="w-5 h-5 inline mr-2" />
                      {t('authModal.login_button')}
                    </>
                  ) : (
                    <>
                      <UserPlus className="w-5 h-5 inline mr-2" />
                      {t('authModal.register_button')}
                    </>
                  )}
                </>
              )}
            </button>
          </div>
        </form>
        )}
        </div>
      </div>

      {/* Terms Modal */}
      <TermsModal isOpen={isTermsModalOpen} onClose={() => setIsTermsModalOpen(false)} />

      {/* Consent Modal */}
      <ConsentModal isOpen={isConsentModalOpen} onClose={() => setIsConsentModalOpen(false)} />

      {/* Forgot Password Modal */}
      <ForgotPasswordModal
        isOpen={isForgotPasswordModalOpen}
        onClose={() => setIsForgotPasswordModalOpen(false)}
        onSuccess={() => {
          setIsForgotPasswordModalOpen(false);
        }}
      />
    </div>
  );
};

