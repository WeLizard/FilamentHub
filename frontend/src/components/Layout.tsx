/** Базовый Layout с Header и навигацией */

import { lazy, ReactNode, Suspense, useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Package, User, LogOut, Shield, MessageCircle, Download, Menu, X, BookOpen, ScanLine } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { authAPI, qrAPI } from '../api/client';
import { ownQrShortCode } from '../utils/qrScanner';
import { LanguageSwitcher } from './LanguageSwitcher';
import { isPluginEmbed, reportAuthStateToPlugin } from '../utils/pluginBridge';
import { EmbedDebugOverlay } from './EmbedDebugOverlay';
import { useTranslation } from 'react-i18next';
import type { QrScanResponse } from '../api/client';
import { filamentPublicPath } from '../utils/catalogUrls';
import { PageBackground } from './PageBackground';
import { SUPPORT_URL } from '../utils/support';
import { GitHubIcon } from './serviceIcons';

const GITHUB_PROJECT_URL = 'https://github.com/WeLizard/FilamentHub';

const AuthModal = lazy(() => import('./AuthModal').then((module) => ({ default: module.AuthModal })));
const FeedbackModal = lazy(() => import('./FeedbackModal').then((module) => ({ default: module.FeedbackModal })));
const QrScannerModal = lazy(() => import('./QrScannerModal').then((module) => ({ default: module.QrScannerModal })));
const QrScanResultModal = lazy(() => import('./QrScanResultModal').then((module) => ({ default: module.QrScanResultModal })));
const Notifications = lazy(() => import('./Notifications').then((module) => ({ default: module.Notifications })));

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
  const [isScannerOpen, setIsScannerOpen] = useState(false);
  const [isScanResolving, setIsScanResolving] = useState(false);
  const [qrScanResult, setQrScanResult] = useState<QrScanResponse | null>(null);

  const handleScanDetected = async (rawCode: string): Promise<boolean> => {
    const code = ownQrShortCode(rawCode);
    if (!code) {
      return false; // не наш QR — сканер продолжит и покажет подсказку
    }
    setIsScanResolving(true);
    try {
      const res = await qrAPI.scan(code);
      if (res?.filament) {
        setIsScannerOpen(false);
        setQrScanResult(res);
        return true;
      }
      return false;
    } catch {
      return false; // не найден — продолжаем сканировать
    } finally {
      setIsScanResolving(false);
    }
  };
  const hasOpenedLoginModalRef = useRef(false);
  const pendingReturnUrlRef = useRef<string | null>(null);

  const sanitizeReturnUrl = (rawValue: string | null): string | null => {
    if (!rawValue) {
      return null;
    }

    try {
      const decoded = decodeURIComponent(rawValue);
      if (!decoded.startsWith('/') || decoded.startsWith('//')) {
        return null;
      }

      return decoded;
    } catch {
      return null;
    }
  };

  // Закрываем мобильное меню при переходе на другую страницу
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location.pathname]);

  // Обработка URL параметра ?auth=login для автоматического открытия модального окна
  useEffect(() => {
    const searchParams = new URLSearchParams(location.search);
    const authParam = searchParams.get('auth');
    const returnUrl = sanitizeReturnUrl(searchParams.get('return_url'));
    
    if (authParam === 'login' && !user && !isAuthModalOpen && !hasOpenedLoginModalRef.current) {
      hasOpenedLoginModalRef.current = true;
      pendingReturnUrlRef.current = returnUrl;
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

  useEffect(() => {
    if (user && !isAuthModalOpen && pendingReturnUrlRef.current) {
      const target = pendingReturnUrlRef.current;
      pendingReturnUrlRef.current = null;
      navigate(target, { replace: true });
    }
  }, [user, isAuthModalOpen, navigate]);

  // Проверяем, запущен ли frontend внутри OrcaSlicer
  const isInOrcaSlicer = typeof window !== 'undefined' && (
    window.filamenthub?.importProfile ||
    window.wx?.postMessage
  );

  // Скрываем хедер/футер и в форковой WebView, и во встроенном режиме плагина
  // (iframe), чтобы навигация внутри iframe не показывала хром сайта.
  const pluginEmbed = isPluginEmbed();
  const hideChrome = isInOrcaSlicer || pluginEmbed;

  // Статус сессии для тулбара шелла плагина: имя + счётчик пресетов
  // (тот же /auth/me/presets-stats, что использовала форковая панель)
  const { data: pluginPresetStats } = useQuery({
    queryKey: ['presets-stats', user?.id],
    queryFn: () => authAPI.getPresetsStats(),
    enabled: pluginEmbed && !!user,
  });
  useEffect(() => {
    if (!pluginEmbed) {
      return;
    }
    if (!user) {
      reportAuthStateToPlugin(null);
      return;
    }
    const stats = pluginPresetStats
      ? ` · ${t('layout.pluginPresetsStats', { total: pluginPresetStats.total_presets, synced: pluginPresetStats.synced_presets })}`
      : '';
    reportAuthStateToPlugin(`${user.username}${stats}`);
  }, [pluginEmbed, user, pluginPresetStats, t]);

  const isActive = (path: string) => location.pathname === path;

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <PageBackground className="app-shell flex flex-col" ambient>

      {/* Header - скрываем если открыто через OrcaSlicer или в iframe плагина */}
      {!hideChrome && (
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
                {/* Название и подзаголовок скрыты, пока в шапке стоит плашка о
                    бете: вместе с ней они не помещаются в строку. Вернуть,
                    когда плашка уедет в подвал. */}
                <div className="hidden shrink-0">
                  <h1 className="text-lg sm:text-2xl font-bold text-white whitespace-nowrap">FilamentHub</h1>
                  <p className="text-xs sm:text-sm text-gray-400 hidden sm:block whitespace-nowrap">{t('layout.tagline')}</p>
                </div>
              </Link>

              {/* Отметка о бете видна всем, обратная связь внутри неё — вошедшим.
                  Пояснение раскрывается поверх страницы, поэтому шапка не растёт. */}
              <div className="ml-2 sm:ml-4 shrink-0 relative group">
                <div className="flex items-center gap-2 rounded-lg border border-amber-400/50 bg-amber-400/15 px-2 py-1 sm:px-2.5 sm:py-1.5">
                  <span className="rounded bg-amber-400 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-gray-900">
                    {t('layout.beta.badge')}
                  </span>
                  {user && (
                    <button
                      onClick={() => setIsFeedbackModalOpen(true)}
                      className="hidden md:flex items-center gap-1.5 rounded-md bg-amber-400/20 hover:bg-amber-400/30 px-2 py-1 text-xs font-medium text-amber-100 hover:text-white transition-colors"
                    >
                      <MessageCircle className="w-3.5 h-3.5" />
                      <span>{t('layout.beta.action')}</span>
                    </button>
                  )}
                </div>

                <div
                  role="tooltip"
                  className="pointer-events-none absolute left-0 top-full z-[60] mt-2 w-72 origin-top -translate-y-1 scale-95 rounded-xl border border-amber-400/30 bg-gray-900/95 p-3 opacity-0 shadow-xl backdrop-blur-sm transition-all duration-150 group-hover:translate-y-0 group-hover:scale-100 group-hover:opacity-100 group-focus-within:translate-y-0 group-focus-within:scale-100 group-focus-within:opacity-100"
                >
                  <p className="text-sm font-semibold text-amber-200">{t('layout.beta.title')}</p>
                  <p className="mt-1 text-xs leading-relaxed text-gray-300">{t('layout.beta.body')}</p>
                </div>
              </div>
            </div>

            {/* Desktop Navigation */}
            <nav className="hidden xl:flex items-center space-x-2 relative z-[100]">
              <button
                onClick={() => setIsScannerOpen(true)}
                className="p-2 text-gray-300 hover:text-white hover:bg-white/10 rounded-lg transition-all"
                aria-label={t('qrScanner.open')}
                title={t('qrScanner.open')}
              >
                <ScanLine className="w-5 h-5" />
              </button>
              {user && (
                <Suspense fallback={null}>
                  <Notifications />
                </Suspense>
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
            <div className="flex xl:hidden items-center space-x-2">
              <button
                onClick={() => setIsScannerOpen(true)}
                className="p-2 text-gray-300 hover:text-white hover:bg-white/10 rounded-lg transition-all"
                aria-label={t('qrScanner.open')}
                title={t('qrScanner.open')}
              >
                <ScanLine className="w-5 h-5" />
              </button>
              {user && (
                <Suspense fallback={null}>
                  <Notifications />
                </Suspense>
              )}
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
          <div className="xl:hidden bg-black/40 backdrop-blur-md border-t border-white/10">
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
                    className="w-full md:hidden flex items-center space-x-3 px-4 py-3 rounded-lg text-purple-300 hover:text-purple-200 hover:bg-purple-600/20 transition-all"
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

              {!user && (
                <div className="border-t border-white/10 pt-3 mt-2 flex items-center justify-between px-1">
                  <span className="text-sm font-medium text-gray-300">{t('settings.language')}</span>
                  <LanguageSwitcher />
                </div>
              )}
            </div>
          </div>
        )}
      </header>
      )}

      {/* Main Content */}
      <main className="relative z-10 flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 py-4 sm:py-8">{children}</main>

      {/* Footer - hidden in OrcaSlicer / plugin iframe */}
      {!hideChrome && (
        <footer className="relative z-10 border-t border-white/10 bg-black/20 backdrop-blur-sm mt-8">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex flex-col sm:flex-row items-center justify-between gap-2 text-[11px] sm:text-xs text-gray-500">
            <span>{t('layout.footer_copyright', { year: new Date().getFullYear() })}</span>
            <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1.5 sm:justify-end sm:gap-x-4">
              <Link to="/about" className="hover:text-gray-300 transition-colors">{t('layout.footer_about')}</Link>
              <Link to="/user-agreement" className="hover:text-gray-300 transition-colors">{t('layout.footer_terms')}</Link>
              <Link to="/privacy-policy" className="hover:text-gray-300 transition-colors">{t('layout.footer_privacy')}</Link>
              <Link to="/personal-data-consent" className="hover:text-gray-300 transition-colors">{t('layout.footer_consent')}</Link>
              <a href="https://db-ip.com" target="_blank" rel="noreferrer" className="hover:text-gray-300 transition-colors">{t('layout.footer_geoip_attribution')}</a>
              <a
                href={GITHUB_PROJECT_URL}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="FilamentHub on GitHub"
                title="GitHub"
                className="inline-flex h-6 w-6 items-center justify-center rounded-md text-gray-500 transition-colors hover:bg-white/5 hover:text-gray-200"
              >
                <GitHubIcon className="h-4 w-4" />
              </a>
              <a
                href={SUPPORT_URL}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`${t('aboutPage.support.title')} — Boosty`}
                title={`${t('aboutPage.support.title')} — Boosty`}
                className="inline-flex items-center gap-1.5 rounded-full border border-[#F15F2C]/25 bg-[#F15F2C]/10 px-2 py-1 text-gray-400 transition-colors hover:border-[#F15F2C]/50 hover:text-gray-200"
              >
                <img src="/brand/boosty-mark.svg" alt="" className="h-3.5 w-3.5" />
                <span>{t('aboutPage.support.action')}</span>
              </a>
            </div>
          </div>
        </footer>
      )}

      {/* Плавающий переключатель языка — только для гостей на десктопе.
          Авторизованные меняют язык в Профиле → Настройки; на мобиле — в меню. */}
      {!hideChrome && !user && (
        <div className="hidden md:flex fixed bottom-4 right-4 z-50 rounded-xl bg-slate-900/95 border border-white/15 shadow-2xl shadow-black/40 p-1 backdrop-blur">
          <LanguageSwitcher compact className="!bg-transparent !border-0 !p-0" />
        </div>
      )}

      {qrScanResult && (
        <Suspense fallback={null}>
          <QrScanResultModal
            result={qrScanResult}
            userId={user?.id ?? null}
            onClose={() => setQrScanResult(null)}
            onRequestLogin={() => setIsAuthModalOpen(true)}
            onOpenMaterial={() => {
              const filament = qrScanResult.filament;
              setQrScanResult(null);
              navigate(`${filamentPublicPath(filament)}?qr=true`);
            }}
            onAddSpool={(placement) => {
              const filamentId = qrScanResult.filament.id;
              setQrScanResult(null);
              navigate(
                `/profile?tab=spools&add_spool=1&filament_id=${filamentId}&source=qr&placement=${placement}`,
              );
            }}
            onOpenSpools={() => {
              setQrScanResult(null);
              navigate('/profile?tab=spools');
            }}
          />
        </Suspense>
      )}

      {/* Auth Modal */}
      {isAuthModalOpen && (
        <Suspense fallback={null}>
          <AuthModal
            isOpen
            onClose={() => {
              setIsAuthModalOpen(false);
              hasOpenedLoginModalRef.current = false; // Сбрасываем флаг при закрытии
              if (!user) {
                pendingReturnUrlRef.current = null;
              }
            }}
            initialMode="login"
          />
        </Suspense>
      )}

      {/* Feedback Modal */}
      {isFeedbackModalOpen && (
        <Suspense fallback={null}>
          <FeedbackModal
            isOpen
            onClose={() => setIsFeedbackModalOpen(false)}
          />
        </Suspense>
      )}

      {isScannerOpen && (
        <Suspense fallback={null}>
          <QrScannerModal
            isOpen
            onClose={() => setIsScannerOpen(false)}
            onDetected={handleScanDetected}
            busy={isScanResolving}
          />
        </Suspense>
      )}

      {/* Экранное логирование ошибок в iframe плагина (DevTools там недоступен) */}
      {isPluginEmbed() && <EmbedDebugOverlay />}
    </PageBackground>
  );
};
