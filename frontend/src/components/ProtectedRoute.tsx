/** Защищенный роут - требует аутентификации */

import { useAuth } from '../contexts/AuthContext';
import { useLocation, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { User, Lock, LogIn, Home, Clock3, Package, Settings, Calculator } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: 'admin' | 'brand';
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, requiredRole }) => {
  const { t } = useTranslation();
  const { isAuthenticated, isLoading, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [countdown, setCountdown] = useState(5);

  const handleLogin = () => {
    const currentPath = `${location.pathname}${location.search}${location.hash}`;
    navigate(`/?auth=login&return_url=${encodeURIComponent(currentPath)}`, { replace: true });
  };

  const handleGoToCatalog = () => {
    navigate('/');
  };

  // Автоматическая переадресация на главную
  useEffect(() => {
    if (!isAuthenticated && !isLoading) {
      setCountdown(5);
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
  }, [isAuthenticated, isLoading, navigate, location.pathname, location.search, location.hash]);

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
        <div className="w-full max-w-2xl px-6">
          <div className="rounded-3xl border border-white/15 bg-black/25 p-8 shadow-2xl shadow-black/30 backdrop-blur-md">
            <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-r from-purple-500/20 to-pink-500/20 ring-1 ring-purple-400/35">
              <Lock className="w-10 h-10 text-white" />
            </div>
            <div className="text-center">
              <h2 className="text-3xl font-bold text-white mb-3">{t('protectedRoute.auth_required_title')}</h2>
              <p className="text-gray-300 mb-6">
                {t('protectedRoute.auth_required_subtitle')}
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 mb-6">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-start gap-3">
                  <Package className="mt-0.5 h-5 w-5 text-purple-300" />
                  <p className="text-sm text-gray-200">{t('protectedRoute.feature_presets')}</p>
                </div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-start gap-3">
                  <Settings className="mt-0.5 h-5 w-5 text-cyan-300" />
                  <p className="text-sm text-gray-200">{t('protectedRoute.feature_profile')}</p>
                </div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-start gap-3">
                  <Calculator className="mt-0.5 h-5 w-5 text-pink-300" />
                  <p className="text-sm text-gray-200">{t('protectedRoute.feature_calculator')}</p>
                </div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-start gap-3">
                  <User className="mt-0.5 h-5 w-5 text-emerald-300" />
                  <p className="text-sm text-gray-200">{t('protectedRoute.feature_account')}</p>
                </div>
              </div>
            </div>

            <div className="mb-6 rounded-2xl border border-purple-400/20 bg-purple-500/10 p-4">
              <div className="flex items-center justify-center gap-2 text-sm text-purple-100">
                <Clock3 className="h-4 w-4" />
                <span>{t('protectedRoute.redirect_countdown', { count: countdown })}</span>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-3 justify-center mb-4">
              <button
                onClick={handleLogin}
                className="flex items-center justify-center space-x-2 px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all shadow-lg shadow-purple-500/25 font-medium"
              >
                <LogIn className="w-5 h-5" />
                <span>{t('protectedRoute.login_button')}</span>
              </button>
              <button
                onClick={handleGoToCatalog}
                className="flex items-center justify-center space-x-2 px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all border border-white/20 font-medium"
              >
                <Home className="w-5 h-5" />
                <span>{t('protectedRoute.home_button')}</span>
              </button>
            </div>

            <p className="text-center text-sm text-gray-400">
              {t('protectedRoute.return_after_login')}
              <span className="ml-1 text-gray-200">{location.pathname}</span>
            </p>
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

