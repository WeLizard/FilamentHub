/** Базовый Layout с Header и навигацией */

import { ReactNode, useState, useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Package, User, LogOut, Shield, MessageCircle, Download } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { AuthModal } from './AuthModal';
import { Notifications } from './Notifications';
import { FeedbackModal } from './FeedbackModal';

interface LayoutProps {
  children: ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [isFeedbackModalOpen, setIsFeedbackModalOpen] = useState(false);
  const hasOpenedLoginModalRef = useRef(false);

  // Обработка URL параметра ?auth=login для автоматического открытия модального окна
  useEffect(() => {
    const searchParams = new URLSearchParams(location.search);
    const authParam = searchParams.get('auth');
    
    if (authParam === 'login' && !user && !isAuthModalOpen && !hasOpenedLoginModalRef.current) {
      hasOpenedLoginModalRef.current = true;
      setIsAuthModalOpen(true);
      // Убираем параметр из URL после небольшой задержки
      setTimeout(() => {
        navigate(location.pathname, { replace: true });
      }, 100);
    }
    
    // Сбрасываем флаг если пользователь залогинился или параметр убран из URL
    if (user || !authParam) {
      hasOpenedLoginModalRef.current = false;
    }
  }, [location.search, user, isAuthModalOpen, navigate, location.pathname]);

  // Проверяем, запущен ли frontend внутри OrcaSlicer
  const isInOrcaSlicer = typeof window !== 'undefined' && (
    (window as any).filamenthub?.importProfile ||
    (window as any).wx?.postMessage
  );

  const isActive = (path: string) => location.pathname === path;

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* Animated Background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-purple-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-blue-500/10 rounded-full blur-3xl animate-pulse delay-1000"></div>
      </div>

      {/* Header - скрываем если открыто через OrcaSlicer */}
      {!isInOrcaSlicer && (
      <header className="relative bg-black/20 backdrop-blur-sm border-b border-white/10 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <Link to="/" className="flex items-center space-x-4">
                <div className="w-12 h-12 flex items-center justify-center">
                  <img 
                    src="/logo.svg" 
                    alt="FilamentHub Logo" 
                    className="w-12 h-12 object-contain"
                  />
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-white">FilamentHub</h1>
                  <p className="text-sm text-gray-400">Интеллектуальный каталог материалов</p>
                </div>
              </Link>
              
              {/* Кнопка обратной связи для бетатестеров (временно справа от лого) - только для авторизованных */}
              {user && (
                <button
                  onClick={() => setIsFeedbackModalOpen(true)}
                  className="ml-4 px-3 py-1.5 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/30 text-purple-300 hover:text-purple-200 text-xs font-medium transition-all flex items-center gap-1.5"
                  title="Обратная связь для бетатестеров"
                >
                  <MessageCircle className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Бета-фидбек</span>
                  <span className="sm:hidden">Фидбек</span>
                </button>
              )}
            </div>

            <nav className="flex items-center space-x-2 relative z-[100]">
              {/* Notifications - только для авторизованных */}
              {user && (
                <Notifications />
              )}

                    <Link
                      to="/"
                      className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-all ${
                        isActive('/')
                          ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25'
                          : 'text-gray-300 hover:text-white hover:bg-white/10'
                      }`}
                    >
                      <Package className="w-4 h-4" />
                      <span>Каталог</span>
                    </Link>

                    <Link
                      to="/download"
                      className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-all ${
                        isActive('/download')
                          ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25'
                          : 'text-gray-300 hover:text-white hover:bg-white/10'
                      }`}
                    >
                      <Download className="w-4 h-4" />
                      <span>Скачать</span>
                    </Link>

              {/* Admin Panel - только для админов */}
              {user?.role === 'admin' && (
                <Link
                  to="/admin"
                  className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-all ${
                    isActive('/admin')
                      ? 'bg-yellow-600 text-white shadow-lg shadow-yellow-500/25'
                      : 'text-gray-300 hover:text-white hover:bg-white/10'
                  }`}
                >
                  <Shield className="w-4 h-4" />
                  <span>Админка</span>
                </Link>
              )}

              {user && (
                <Link
                  to="/profile"
                  className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-all ${
                    isActive('/profile')
                      ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25'
                      : 'text-gray-300 hover:text-white hover:bg-white/10'
                  }`}
                >
                  <User className="w-4 h-4" />
                  <span>Профиль</span>
                </Link>
              )}

              {user ? (
                <button
                  onClick={handleLogout}
                  className="flex items-center space-x-2 px-4 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg transition-all"
                >
                  <LogOut className="w-4 h-4" />
                  <span>Выйти</span>
                </button>
              ) : (
                <button
                  onClick={() => setIsAuthModalOpen(true)}
                  className="flex items-center space-x-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-all"
                >
                  <User className="w-4 h-4" />
                  <span>Войти</span>
                </button>
              )}
            </nav>
          </div>
        </div>
      </header>
      )}

      {/* Main Content */}
      <main className="relative max-w-7xl mx-auto px-6 py-8 z-10">{children}</main>

      {/* Auth Modal */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => {
          setIsAuthModalOpen(false);
          hasOpenedLoginModalRef.current = false; // Сбрасываем флаг при закрытии
        }}
        initialMode="login"
      />

      {/* Feedback Modal */}
      <FeedbackModal
        isOpen={isFeedbackModalOpen}
        onClose={() => setIsFeedbackModalOpen(false)}
      />
    </div>
  );
};

