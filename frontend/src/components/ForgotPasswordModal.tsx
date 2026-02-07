/** Модальное окно восстановления пароля */

import { useState, FormEvent } from 'react';
import { Mail, X, CheckCircle, AlertCircle, Loader } from 'lucide-react';
import { authAPI } from '../api/client';
import { useHeaderVisible } from '../hooks/useHeaderVisible';

interface ForgotPasswordModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export const ForgotPasswordModal: React.FC<ForgotPasswordModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const isHeaderVisible = useHeaderVisible();
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await authAPI.forgotPassword(email);
      setIsSuccess(true);
      setEmail('');
    } catch (err: any) {
      let errorMessage = 'Произошла ошибка при отправке запроса. Попробуйте позже.';
      
      if (err.response) {
        const status = err.response.status;
        const detail = err.response.data?.detail;
        
        if (status === 429) {
          errorMessage = 'Слишком много запросов. Попробуйте позже.';
        } else if (typeof detail === 'string') {
          errorMessage = detail;
        }
      } else if (err.request) {
        errorMessage = 'Не удалось подключиться к серверу. Проверьте подключение к интернету.';
      }
      
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    if (!isLoading) {
      setEmail('');
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
            disabled={isLoading}
            className="absolute top-4 right-4 p-2 text-gray-400 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <X className="w-5 h-5" />
          </button>

          <div className="text-center mb-8">
            <div className="w-16 h-16 flex items-center justify-center mx-auto mb-4">
              <img src="/logo.svg" alt="FilamentHub Logo" className="w-16 h-16 object-contain" />
            </div>
            <h2 className="text-2xl font-bold text-white mb-2">Восстановление пароля</h2>
            <p className="text-gray-300">Введите адрес эл. почты для получения инструкций</p>
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
                <h3 className="text-xl font-bold text-white mb-2">Проверьте почту</h3>
                <p className="text-gray-300">
                  Если указанный адрес существует в системе, на него будет отправлена инструкция по восстановлению пароля.
                </p>
                <p className="text-gray-400 text-sm mt-2">
                  Ссылка действительна в течение 1 часа.
                </p>
              </div>
              <button
                onClick={handleClose}
                className="w-full mt-6 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white py-3 px-6 rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40"
              >
                Понятно
              </button>
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
                  <label className="block text-gray-300 mb-2">Эл. почта</label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5 pointer-events-none" />
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      disabled={isLoading}
                      className="w-full pl-10 pr-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                      placeholder="your@email.com"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isLoading || !email}
                  className="w-full mt-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white py-3 px-6 rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
                >
                  {isLoading ? (
                    <>
                      <Loader className="w-5 h-5 animate-spin" />
                      <span>Отправка...</span>
                    </>
                  ) : (
                    <span>Отправить инструкцию</span>
                  )}
                </button>

                <button
                  type="button"
                  onClick={handleClose}
                  disabled={isLoading}
                  className="w-full text-gray-400 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Вернуться к входу
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};

