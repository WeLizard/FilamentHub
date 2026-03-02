/** Базовый Layout с Header и навигацией */

import { ReactNode, useState, useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Package, User, LogOut, Shield, MessageCircle, Download, Menu, X, BookOpen, Calculator } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { AuthModal } from './AuthModal';
import { Notifications } from './Notifications';
import { FeedbackModal } from './FeedbackModal';
import { useTranslation } from 'react-i18next';

interface LayoutProps {
  children: ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [isFeedbackModalOpen, setIsFeedbackModalOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const hasOpenedLoginModalRef = useRef(false);

  // Закрываем мобильное меню при переходе на другую страницу
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location.pathname]);

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
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 sm:py-4">
          <div className="flex items-center justify-between">
            {/* Logo */}
            <div className="flex items-center space-x-2 sm:space-x-4">
              <Link to="/" className="flex items-center space-x-2 sm:space-x-4">
                <div className="w-10 h-10 sm:w-12 sm:h-12 flex items-center justify-center">
                  <img 
                    src="/logo.svg" 
                    alt="FilamentHub Logo" 
                    className="w-10 h-10 sm:w-12 sm:h-12 object-contain"
                  />
                </div>
                <div className="hidden xs:block">
                  <h1 className="text-lg sm:text-2xl font-bold text-white">FilamentHub</h1>
                  <p className="text-xs sm:text-sm text-gray-400 hidden sm:block">{t('layout.tagline')}</p>
                </div>
              </Link>
              
              {/* Кнопка обратной связи - скрыта на мобильных, показывается в меню */}
              {user && (
                <button
                  onClick={() => setIsFeedbackModalOpen(true)}
                  className="hidden md:flex ml-4 px-3 py-1.5 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/30 text-purple-300 hover:text-purple-200 text-xs font-medium transition-all items-center gap-1.5"
                  title={t('layout.feedback_tooltip')}
                >
                  <MessageCircle className="w-3.5 h-3.5" />
                  <span>{t('layout.feedback_button')}</span>
                </button>
              )}
            </div>

            {/* Desktop Navigation */}
            <nav className="hidden md:flex items-center space-x-2 relative z-[100]">
              {user && <Notifications />}

              <Link
                to="/"
                className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-all ${
                  isActive('/')
                    ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25'
                    : 'text-gray-300 hover:text-white hover:bg-white/10'
                }`}
              >
                <Package className="w-4 h-4" />
                <span>{t('layout.nav_catalog')}</span>
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
                <span>{t('layout.nav_download')}</span>
              </Link>

              <Link
                to="/wiki"
                className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-all ${
                  isActive('/wiki')
                    ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25'
                    : 'text-gray-300 hover:text-white hover:bg-white/10'
                }`}
              >
                <BookOpen className="w-4 h-4" />
                <span>{t('layout.nav_wiki')}</span>
              </Link>

              <Link
                to="/calculator"
                className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-all ${
                  isActive('/calculator')
                    ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25'
                    : 'text-gray-300 hover:text-white hover:bg-white/10'
                }`}
              >
                <Calculator className="w-4 h-4" />
                <span>{t('layout.nav_calculator')}</span>
              </Link>

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
                  <span>{t('layout.nav_admin')}</span>
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
                  <span>{t('layout.nav_profile')}</span>
                </Link>
              )}

              {user ? (
                <button
                  onClick={handleLogout}
                  className="flex items-center space-x-2 px-4 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg transition-all"
                >
                  <LogOut className="w-4 h-4" />
                  <span>{t('layout.nav_logout')}</span>
                </button>
              ) : (
                <button
                  onClick={() => setIsAuthModalOpen(true)}
                  className="flex items-center space-x-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-all"
                >
                  <User className="w-4 h-4" />
                  <span>{t('layout.nav_login')}</span>
                </button>
              )}
            </nav>

            {/* Mobile: Notifications + Hamburger */}
            <div className="flex md:hidden items-center space-x-2">
              {user && <Notifications />}
              <button
                onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                className="p-2 text-gray-300 hover:text-white hover:bg-white/10 rounded-lg transition-all"
                aria-label={t('layout.nav_menu')}
              >
                {isMobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
              </button>
            </div>
          </div>
        </div>

        {/* Mobile Menu */}
        {isMobileMenuOpen && (
          <div className="md:hidden bg-black/40 backdrop-blur-md border-t border-white/10">
            <div className="px-4 py-3 space-y-2">
              <Link
                to="/"
                className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-all ${
                  isActive('/')
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-300 hover:text-white hover:bg-white/10'
                }`}
              >
                <Package className="w-5 h-5" />
                <span className="font-medium">{t('layout.nav_catalog')}</span>
              </Link>

              <Link
                to="/download"
                className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-all ${
                  isActive('/download')
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-300 hover:text-white hover:bg-white/10'
                }`}
              >
                <Download className="w-5 h-5" />
                <span className="font-medium">{t('layout.nav_download')}</span>
              </Link>

              <Link
                to="/wiki"
                className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-all ${
                  isActive('/wiki')
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-300 hover:text-white hover:bg-white/10'
                }`}
              >
                <BookOpen className="w-5 h-5" />
                <span className="font-medium">{t('layout.nav_wiki')}</span>
              </Link>

              <Link
                to="/calculator"
                className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-all ${
                  isActive('/calculator')
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-300 hover:text-white hover:bg-white/10'
                }`}
              >
                <Calculator className="w-5 h-5" />
                <span className="font-medium">{t('layout.nav_calculator')}</span>
              </Link>

              {user?.role === 'admin' && (
                <Link
                  to="/admin"
                  className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-all ${
                    isActive('/admin')
                      ? 'bg-yellow-600 text-white'
                      : 'text-gray-300 hover:text-white hover:bg-white/10'
                  }`}
                >
                  <Shield className="w-5 h-5" />
                  <span className="font-medium">{t('layout.nav_admin')}</span>
                </Link>
              )}

              {user && (
                <>
                  <Link
                    to="/profile"
                    className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-all ${
                      isActive('/profile')
                        ? 'bg-purple-600 text-white'
                        : 'text-gray-300 hover:text-white hover:bg-white/10'
                    }`}
                  >
                    <User className="w-5 h-5" />
                    <span className="font-medium">{t('layout.nav_profile')}</span>
                  </Link>

                  <button
                    onClick={() => setIsFeedbackModalOpen(true)}
                    className="w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-purple-300 hover:text-purple-200 hover:bg-purple-600/20 transition-all"
                  >
                    <MessageCircle className="w-5 h-5" />
                    <span className="font-medium">{t('layout.feedback_button')}</span>
                  </button>

                  <div className="border-t border-white/10 pt-2 mt-2">
                    <button
                      onClick={handleLogout}
                      className="w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-red-400 hover:bg-red-600/20 transition-all"
                    >
                      <LogOut className="w-5 h-5" />
                      <span className="font-medium">{t('layout.nav_logout')}</span>
                    </button>
                  </div>
                </>
              )}

              {!user && (
                <button
                  onClick={() => {
                    setIsAuthModalOpen(true);
                    setIsMobileMenuOpen(false);
                  }}
                  className="w-full flex items-center justify-center space-x-2 px-4 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-all font-medium"
                >
                  <User className="w-5 h-5" />
                  <span>{t('layout.nav_login')}</span>
                </button>
              )}
            </div>
          </div>
        )}
      </header>
      )}

      {/* Main Content */}
      <main className="relative max-w-7xl mx-auto px-4 sm:px-6 py-4 sm:py-8 z-10">{children}</main>

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

