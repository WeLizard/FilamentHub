import { useState } from 'react';
import { Settings, LogIn, AlertTriangle } from 'lucide-react';
import { AuthModal } from './AuthModal';

interface MaintenancePageProps {
  message?: string;
  onLoginSuccess?: () => void;
}

export function MaintenancePage({ message, onLoginSuccess }: MaintenancePageProps) {
  const [showAuthModal, setShowAuthModal] = useState(false);

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 flex items-center justify-center p-4">
      <div className="max-w-md w-full text-center">
        {/* Icon */}
        <div className="mb-8">
          <div className="w-24 h-24 mx-auto bg-yellow-500/20 rounded-full flex items-center justify-center">
            <Settings className="w-12 h-12 text-yellow-400 animate-spin-slow" />
          </div>
        </div>

        {/* Title */}
        <h1 className="text-3xl font-bold text-white mb-4">
          Технические работы
        </h1>

        {/* Message */}
        <p className="text-gray-300 mb-2">
          Сайт временно недоступен.
        </p>
        {message && (
          <p className="text-yellow-400 mb-6">
            {message}
          </p>
        )}
        {!message && (
          <p className="text-gray-400 mb-6">
            Мы работаем над улучшением сервиса. Пожалуйста, попробуйте позже.
          </p>
        )}

        {/* Warning box */}
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 mb-8">
          <div className="flex items-center gap-2 text-yellow-400">
            <AlertTriangle className="w-5 h-5" />
            <span className="font-medium">Ведутся технические работы</span>
          </div>
        </div>

        {/* Admin login button */}
        <button
          onClick={() => setShowAuthModal(true)}
          className="text-gray-500 hover:text-gray-300 text-sm flex items-center gap-2 mx-auto transition-colors"
        >
          <LogIn className="w-4 h-4" />
          Вход для администратора
        </button>
      </div>

      {/* Auth Modal */}
      <AuthModal
        isOpen={showAuthModal}
        onClose={() => {
          setShowAuthModal(false);
          // Если onLoginSuccess передан — вызываем его для обновления состояния
          if (onLoginSuccess) {
            onLoginSuccess();
          }
        }}
        initialMode="login"
      />

      <style>{`
        @keyframes spin-slow {
          from {
            transform: rotate(0deg);
          }
          to {
            transform: rotate(360deg);
          }
        }
        .animate-spin-slow {
          animation: spin-slow 8s linear infinite;
        }
      `}</style>
    </div>
  );
}
