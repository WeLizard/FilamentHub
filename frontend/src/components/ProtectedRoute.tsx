/** Защищенный роут - требует аутентификации */

import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { User, Lock } from 'lucide-react';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 bg-gradient-to-r from-purple-500 to-pink-500 rounded-xl flex items-center justify-center mx-auto mb-4 animate-pulse">
            <User className="w-8 h-8 text-white" />
          </div>
          <div className="text-white text-xl">Загрузка...</div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="text-center max-w-md mx-auto px-6">
          <div className="w-20 h-20 bg-gradient-to-r from-purple-500 to-pink-500 rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-lg shadow-purple-500/25">
            <Lock className="w-10 h-10 text-white" />
          </div>
          <h2 className="text-3xl font-bold text-white mb-4">Требуется авторизация</h2>
          <p className="text-gray-300 mb-6">
            Для доступа к этой странице необходимо войти в систему. Используйте кнопку "Войти" в правом верхнем углу.
          </p>
          <div className="bg-white/10 backdrop-blur-sm rounded-xl p-4 border border-white/20">
            <p className="text-gray-400 text-sm">
              После входа вы сможете создавать пресеты, управлять материалами и использовать все возможности платформы.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
};

