/** Модальное окно авторизации */

import { useState, FormEvent } from 'react';
import { Mail, Lock, LogIn, UserPlus, User, Factory, Package, X, Check, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { Captcha } from './Captcha';
import { TermsModal } from './TermsModal';
import { ConsentModal } from './ConsentModal';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialMode?: 'login' | 'register';
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onClose, initialMode = 'login' }) => {
  const [authMode, setAuthMode] = useState<'login' | 'register'>(initialMode);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [username, setUsername] = useState('');
  const [role, setRole] = useState<'user' | 'brand'>('user');
  const [agreed, setAgreed] = useState(false);
  const [captchaValue, setCaptchaValue] = useState('');
  const [captchaVerified, setCaptchaVerified] = useState(false);
  const [showCaptcha, setShowCaptcha] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isTermsModalOpen, setIsTermsModalOpen] = useState(false);
  const [isConsentModalOpen, setIsConsentModalOpen] = useState(false);

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

    if (strength <= 2) return { strength, label: 'Слабый', color: 'text-red-400' };
    if (strength <= 4) return { strength, label: 'Средний', color: 'text-yellow-400' };
    return { strength, label: 'Сильный', color: 'text-green-400' };
  };

  const passwordStrength = getPasswordStrength(password);

  if (!isOpen) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      if (authMode === 'login') {
        await login(email, password);
        onClose();
        setEmail('');
        setPassword('');
      } else {
        // Валидация без очистки полей
        if (!agreed) {
          setError('Необходимо согласиться с условиями использования');
          setIsLoading(false);
          return;
        }
        if (password !== confirmPassword) {
          setError('Пароли не совпадают');
          setIsLoading(false);
          return;
        }
        if (password.length < 8) {
          setError('Пароль должен содержать минимум 8 символов');
          setIsLoading(false);
          return;
        }
        
        // Показываем капчу при первой попытке регистрации
        if (!showCaptcha) {
          setShowCaptcha(true);
          setIsLoading(false);
          return;
        }
        
        // Проверяем капчу только если она уже показана
        if (!captchaVerified) {
          setError('Необходимо пройти проверку капчи');
          setIsLoading(false);
          return;
        }
        
        // Все проверки пройдены - регистрируем
        await register({ email, username, password, role });
        onClose();
        // Очищаем поля только после успешной регистрации
        setEmail('');
        setPassword('');
        setConfirmPassword('');
        setUsername('');
        setAgreed(false);
        setCaptchaValue('');
        setCaptchaVerified(false);
        setShowCaptcha(false);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Произошла ошибка при авторизации');
      setIsLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    // TODO: Реализовать Google OAuth
    setError('Вход через Google будет доступен в ближайшее время');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      ></div>

      {/* Modal */}
      <div className="relative w-full max-w-md bg-white/10 backdrop-blur-sm rounded-2xl p-8 border border-white/20 shadow-xl z-10">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 text-gray-400 hover:text-white transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-gradient-to-r from-purple-500 to-pink-500 rounded-xl flex items-center justify-center mx-auto mb-4 shadow-lg shadow-purple-500/25">
            <Package className="w-8 h-8 text-white" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Добро пожаловать в FilamentHub</h2>
          <p className="text-gray-300">Войдите в систему для доступа к персональному кабинету</p>
        </div>

        {/* Tabs */}
        <div className="flex mb-6">
          <button
            onClick={() => {
              setAuthMode('login');
              setShowCaptcha(false);
              setCaptchaValue('');
              setCaptchaVerified(false);
            }}
            className={`flex-1 py-3 px-4 rounded-l-xl transition-all ${
              authMode === 'login'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            Вход
          </button>
          <button
            onClick={() => {
              setAuthMode('register');
              setShowCaptcha(false);
              setCaptchaValue('');
              setCaptchaVerified(false);
            }}
            className={`flex-1 py-3 px-4 rounded-r-xl transition-all ${
              authMode === 'register'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            Регистрация
          </button>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-4 p-3 bg-red-500/20 border border-red-500/30 rounded-xl text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Google Login Button */}
        <button
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
          <span>Войти через Google</span>
        </button>

        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-white/20"></div>
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-2 bg-white/10 text-gray-400">или</span>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label className="block text-gray-300 mb-2">Email</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full pl-10 pr-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                  placeholder="your@email.com"
                />
              </div>
            </div>

            {authMode === 'register' && (
              <div>
                <label className="block text-gray-300 mb-2">Имя пользователя</label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    className="w-full pl-10 pr-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                    placeholder="username"
                  />
                </div>
              </div>
            )}

            <div>
              <label className="block text-gray-300 mb-2">Пароль</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full pl-10 pr-12 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
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
                    Минимум 8 символов, включая заглавные и строчные буквы, цифры
                  </p>
                </div>
              )}
            </div>

            {/* Поле подтверждения пароля (только для регистрации) */}
            {authMode === 'register' && (
              <div>
                <label className="block text-gray-300 mb-2">Подтвердите пароль</label>
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
                {confirmPassword && password !== confirmPassword && (
                  <p className="mt-1 text-xs text-red-400">Пароли не совпадают</p>
                )}
                {confirmPassword && password === confirmPassword && (
                  <p className="mt-1 text-xs text-green-400">✓ Пароли совпадают</p>
                )}
              </div>
            )}

            {authMode === 'register' && (
              <>
                <div>
                  <label className="block text-gray-300 mb-2">Тип аккаунта</label>
                  <div className="flex space-x-2">
                    <button
                      type="button"
                      onClick={() => setRole('user')}
                      className={`flex-1 py-2 px-4 rounded-lg transition-all border ${
                        role === 'user'
                          ? 'bg-purple-600 text-white border-purple-500'
                          : 'bg-white/10 hover:bg-white/20 text-white border-white/20'
                      }`}
                    >
                      <User className="w-4 h-4 inline mr-2" />
                      Пользователь
                    </button>
                    <button
                      type="button"
                      onClick={() => setRole('brand')}
                      className={`flex-1 py-2 px-4 rounded-lg transition-all border ${
                        role === 'brand'
                          ? 'bg-purple-600 text-white border-purple-500'
                          : 'bg-white/10 hover:bg-white/20 text-white border-white/20'
                      }`}
                    >
                      <Factory className="w-4 h-4 inline mr-2" />
                      Производитель
                    </button>
                  </div>
                </div>

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
                    Я принимаю{' '}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setIsTermsModalOpen(true);
                      }}
                      className="text-purple-400 hover:text-purple-300 underline"
                    >
                      условия Пользовательского соглашения
                    </button>{' '}
                    и даю{' '}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setIsConsentModalOpen(true);
                      }}
                      className="text-purple-400 hover:text-purple-300 underline"
                    >
                      согласие на обработку персональных данных
                    </button>
                  </label>
                </div>

                {/* Captcha - показываем только после первой попытки регистрации */}
                {showCaptcha && (
                  <Captcha
                    value={captchaValue}
                    onChange={setCaptchaValue}
                    onVerify={setCaptchaVerified}
                  />
                )}
              </>
            )}

            <button
              type="submit"
              disabled={isLoading || (authMode === 'register' && (!agreed || (showCaptcha && !captchaVerified)))}
              className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white py-3 px-6 rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                'Загрузка...'
              ) : (
                <>
                  {authMode === 'login' ? (
                    <>
                      <LogIn className="w-5 h-5 inline mr-2" />
                      Войти
                    </>
                  ) : (
                    <>
                      <UserPlus className="w-5 h-5 inline mr-2" />
                      Зарегистрироваться
                    </>
                  )}
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Terms Modal */}
      <TermsModal isOpen={isTermsModalOpen} onClose={() => setIsTermsModalOpen(false)} />

      {/* Consent Modal */}
      <ConsentModal isOpen={isConsentModalOpen} onClose={() => setIsConsentModalOpen(false)} />
    </div>
  );
};

