/** Защищенный роут - требует аутентификации */

import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { User, Lock, LogIn, Package, ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: 'admin' | 'brand';
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, requiredRole }) => {
  const { t } = useTranslation();
  const { isAuthenticated, isLoading, user } = useAuth();
  const navigate = useNavigate();
  const [countdown, setCountdown] = useState(5);

  const handleLogin = () => {
    // Открываем модальное окно авторизации через URL параметр
    navigate(`${window.location.pathname}?auth=login`, { replace: true });
  };

  const handleGoToCatalog = () => {
    navigate('/');
  };

  // Автоматическая переадресация на главную
  useEffect(() => {
    if (!isAuthenticated && !isLoading) {
      const timer = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(timer);
            navigate('/');
            return 0;
          }
          return prev - 1;
        });
      }, 1000);

      return () => clearInterval(timer);
    }
  }, [isAuthenticated, isLoading, navigate]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 bg-gradient-to-r from-purple-500 to-pink-500 rounded-xl flex items-center justify-center mx-auto mb-4 animate-pulse">
            <User className="w-8 h-8 text-white" />
          </div>
          <div className="text-white text-xl">{t('protectedRoute.loading')}</div>
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
          <h2 className="text-3xl font-bold text-white mb-4">{t('protectedRoute.auth_required_title')}</h2>
          <p className="text-gray-300 mb-6">
            {t('protectedRoute.auth_required_subtitle')}
          </p>
          <div className="bg-white/10 backdrop-blur-sm rounded-xl p-4 border border-white/20 mb-6">
            <p className="text-gray-400 text-sm">
              {t('protectedRoute.auth_required_tip')}
            </p>
          </div>
          
          {/* Кнопки действий */}
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <button
              onClick={handleLogin}
              className="flex items-center justify-center space-x-2 px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-lg transition-all shadow-lg shadow-purple-500/25 font-medium"
            >
              <LogIn className="w-5 h-5" />
              <span>{t('protectedRoute.login_button')}</span>
            </button>
            <button
              onClick={handleGoToCatalog}
              className="flex items-center justify-center space-x-2 px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all border border-white/20 font-medium"
            >
              <Package className="w-5 h-5" />
              <span>{t('protectedRoute.catalog_button')}</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Проверка роли
  if (requiredRole && user?.role !== requiredRole) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="text-center max-w-md mx-auto px-6">
          <div className="w-20 h-20 bg-gradient-to-r from-red-500 to-orange-500 rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-lg shadow-red-500/25">
            <Lock className="w-10 h-10 text-white" />
          </div>
          <h2 className="text-3xl font-bold text-white mb-4">{t('protectedRoute.access_denied_title')}</h2>
          <p className="text-gray-300 mb-6">
            {requiredRole === 'admin' ? t('protectedRoute.access_denied_admin') : t('protectedRoute.access_denied_brand')}
          </p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
};

