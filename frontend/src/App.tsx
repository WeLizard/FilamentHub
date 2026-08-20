import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Layout } from './components/Layout';
import { CatalogPage } from './pages/CatalogPage';
import { ToastContainer, toast } from './components/Toast';
import { useCurrencyCatalogue } from './hooks/useCurrencyCatalogue';
import { useOrcaSlicerNotifications } from './hooks/useOrcaSlicerNotifications';
import { useTokenRefresh } from './hooks/useTokenRefresh';
import { lazy, Suspense, useEffect, useState } from 'react';
import { isPluginEmbed, subscribeToPluginNavigation, subscribeToPluginSyncResult, subscribeToPluginRecoverList, sendRecoverImport, type RecoverItem } from './utils/pluginBridge';
import { useAuth } from './contexts/AuthContext';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

// Lazy-loaded pages (code splitting)
const FilamentDetailPage = lazy(() => import('./pages/FilamentDetailPage').then(m => ({ default: m.FilamentDetailPage })));
const TermsPage = lazy(() => import('./pages/TermsPage').then(m => ({ default: m.TermsPage })));
const ConsentPage = lazy(() => import('./pages/ConsentPage').then(m => ({ default: m.ConsentPage })));
const AboutPage = lazy(() => import('./pages/AboutPage').then(m => ({ default: m.AboutPage })));
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage').then(m => ({ default: m.ResetPasswordPage })));
const OAuthCallbackPage = lazy(() => import('./pages/OAuthCallbackPage').then(m => ({ default: m.OAuthCallbackPage })));
const OAuthPluginStartPage = lazy(() => import('./pages/OAuthPluginStartPage').then(m => ({ default: m.OAuthPluginStartPage })));
const VerifyEmailPage = lazy(() => import('./pages/VerifyEmailPage').then(m => ({ default: m.VerifyEmailPage })));
const ConfirmEmailChangePage = lazy(() => import('./pages/ConfirmEmailChangePage').then(m => ({ default: m.ConfirmEmailChangePage })));
const BrandInvitePage = lazy(() => import('./pages/BrandInvitePage').then(m => ({ default: m.BrandInvitePage })));
const DownloadPage = lazy(() => import('./pages/DownloadPage').then(m => ({ default: m.DownloadPage })));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage').then(m => ({ default: m.NotFoundPage })));
const ProfilePage = lazy(() => import('./pages/ProfilePage').then(m => ({ default: m.ProfilePage })));
const CalculatorPage = lazy(() => import('./pages/CalculatorPage').then(m => ({ default: m.CalculatorPage })));
const CrmWorkspacePage = lazy(() => import('./pages/CrmWorkspacePage').then(m => ({ default: m.CrmWorkspacePage })));
const BrandDetailPage = lazy(() => import('./pages/BrandDetailPage').then(m => ({ default: m.BrandDetailPage })));
const AdminPanel = lazy(() => import('./pages/AdminPanel').then(m => ({ default: m.AdminPanel })));
const WikiPage = lazy(() => import('./pages/WikiPage').then(m => ({ default: m.WikiPage })));
const WikiWorkspacePage = lazy(() => import('./pages/WikiWorkspacePage').then(m => ({ default: m.WikiWorkspacePage })));
const WikiCategoryPage = lazy(() => import('./pages/WikiCategoryPage').then(m => ({ default: m.WikiCategoryPage })));
const WikiArticlePage = lazy(() => import('./pages/WikiArticlePage').then(m => ({ default: m.WikiArticlePage })));
const PrivacyPolicyPage = lazy(() => import('./pages/PrivacyPolicyPage').then(m => ({ default: m.PrivacyPolicyPage })));
const SharedQuotePage = lazy(() => import('./pages/SharedQuotePage').then(m => ({ default: m.SharedQuotePage })));
const FeedbackThreadPage = lazy(() => import('./pages/FeedbackThreadPage').then(m => ({ default: m.FeedbackThreadPage })));
const Notifications = lazy(() => import('./components/Notifications').then(m => ({ default: m.Notifications })));
const RecoverPresetsModal = lazy(() => import('./components/RecoverPresetsModal').then(m => ({ default: m.RecoverPresetsModal })));
const LegalOnboardingModal = lazy(() => import('./components/LegalOnboardingModal').then(m => ({ default: m.LegalOnboardingModal })));
const MaintenancePage = lazy(() => import('./components/MaintenancePage').then(m => ({ default: m.MaintenancePage })));
const DevUiKitPage = import.meta.env.DEV
  ? lazy(() => import('./pages/dev/UiKitPage').then(m => ({ default: m.UiKitPage })))
  : null;

function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <Loader2 className="w-8 h-8 text-purple-400 animate-spin" />
    </div>
  );
}

const LEGAL_PATHS = ['/user-agreement', '/privacy-policy', '/personal-data-consent'];

function AppContent() {
  // Обработчик уведомлений от OrcaSlicer
  useOrcaSlicerNotifications();
  useCurrencyCatalogue();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const location = useLocation();
  const { user, isMaintenanceMode, maintenanceMessage, clearMaintenanceMode } = useAuth();
  useTokenRefresh(Boolean(user));
  // The onboarding modal links to these pages; covering them makes the documents
  // a person is asked to accept unreadable.
  const onLegalPage = LEGAL_PATHS.includes(location.pathname);
  
  // Проверяем, запущен ли frontend внутри OrcaSlicer
  const isInOrcaSlicer = typeof window !== 'undefined' && (
    window.filamenthub?.importProfile ||
    window.wx?.postMessage
  );
  
  // Добавляем глобальную функцию для навигации из OrcaSlicer без перезагрузки страницы
  useEffect(() => {
    if (typeof window !== 'undefined') {
      // Создаём объект filamenthub если его нет, добавляем функцию навигации
      window.filamenthub = window.filamenthub ?? {};
      window.filamenthub.navigate = (path: string) => {
        navigate(path);
      };
    }
  }, [navigate]);

  // Навигация от кнопок шелла плагина OrcaSlicer (Catalog/Profile/Wiki над iframe)
  useEffect(() => {
    if (!isPluginEmbed()) {
      return;
    }
    return subscribeToPluginNavigation(navigate);
  }, [navigate]);

  useEffect(() => {
    if (!isPluginEmbed()) {
      return;
    }
    return subscribeToPluginSyncResult((result) => {
      toast.success(
        result.text,
        result.draftCount > 0 ? 10_000 : undefined,
        'sync',
        result.draftCount > 0
          ? {
              label: t('profilePage.openDraftQueue'),
              onClick: () => navigate('/profile?tab=presets&preset_filter=drafts'),
            }
          : undefined,
      );
      void queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
      void queryClient.invalidateQueries({ queryKey: ['user-presets'] });
      void queryClient.invalidateQueries({ queryKey: ['preset-draft-queue'] });
      void queryClient.invalidateQueries({ queryKey: ['preset-stats'] });
    });
  }, [navigate, queryClient, t]);

  const [recoverItems, setRecoverItems] = useState<RecoverItem[] | null>(null);
  useEffect(() => {
    if (!isPluginEmbed()) {
      return;
    }
    return subscribeToPluginRecoverList((items) => setRecoverItems(items));
  }, []);

  // Показываем страницу технических работ если включён maintenance mode
  // НО: если пользователь уже авторизован как админ — показываем сайт
  if (isMaintenanceMode && (!user || user.role !== 'admin')) {
    return (
      <>
        <ToastContainer />
        <Suspense fallback={<PageLoader />}>
          <MaintenancePage
            message={maintenanceMessage || undefined}
            onLoginSuccess={() => {
              // После успешного входа — обновляем состояние
              clearMaintenanceMode();
            }}
          />
        </Suspense>
      </>
    );
  }

  return (
    <>
      <ToastContainer />
      {user?.legal_onboarding_required && !onLegalPage && (
        <Suspense fallback={null}>
          <LegalOnboardingModal />
        </Suspense>
      )}
      {recoverItems && (
        <Suspense fallback={null}>
          <RecoverPresetsModal
            items={recoverItems}
            onClose={() => setRecoverItems(null)}
            onImport={(names) => {
              sendRecoverImport(names);
              setRecoverItems(null);
            }}
          />
        </Suspense>
      )}
      {/* Плавающая кнопка уведомлений для OrcaSlicer (когда нет хедера) */}
      {isInOrcaSlicer && user && (
        <Suspense fallback={null}>
          <Notifications floating={true} />
        </Suspense>
      )}
      <Routes>
        <Route
          path="/"
          element={
            <Layout>
              <CatalogPage />
            </Layout>
          }
        />
        <Route
          path="/filaments/:id"
          element={
            <Layout>
              <Suspense fallback={<PageLoader />}>
                <FilamentDetailPage />
              </Suspense>
            </Layout>
          }
        />
        <Route
          path="/brands/:brandSlug/filaments/:filamentSlug"
          element={
            <Layout>
              <Suspense fallback={<PageLoader />}>
                <FilamentDetailPage />
              </Suspense>
            </Layout>
          }
        />
        <Route
          path="/brands/:identifier"
          element={
            <Layout>
              <Suspense fallback={<PageLoader />}>
                <BrandDetailPage />
              </Suspense>
            </Layout>
          }
        />
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <Layout>
                <Suspense fallback={<PageLoader />}>
                  <ProfilePage />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/calculator"
          element={
            <ProtectedRoute>
              <Layout>
                <Suspense fallback={<PageLoader />}>
                  <CalculatorPage />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/feedback/:feedbackId"
          element={
            <ProtectedRoute>
              <Layout>
                <Suspense fallback={<PageLoader />}>
                  <FeedbackThreadPage />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/workspace"
          element={
            <ProtectedRoute>
              <Layout>
                <Suspense fallback={<PageLoader />}>
                  <CrmWorkspacePage />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedRoute requiredRole="admin">
              <Suspense fallback={<PageLoader />}>
                <AdminPanel />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/download"
          element={
            <Layout>
              <Suspense fallback={<PageLoader />}>
                <DownloadPage />
              </Suspense>
            </Layout>
          }
        />
        <Route
          path="/wiki"
          element={
            <Layout>
              <Suspense fallback={<PageLoader />}>
                <WikiPage />
              </Suspense>
            </Layout>
          }
        />
        <Route
          path="/wiki/workspace"
          element={
            <ProtectedRoute>
              <Layout>
                <Suspense fallback={<PageLoader />}>
                  <WikiWorkspacePage />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/wiki/:slug"
          element={
            <Layout>
              <Suspense fallback={<PageLoader />}>
                <WikiCategoryPage />
              </Suspense>
            </Layout>
          }
        />
        <Route
          path="/wiki/articles/:slug"
          element={
            <Layout>
              <Suspense fallback={<PageLoader />}>
                <WikiArticlePage />
              </Suspense>
            </Layout>
          }
        />
        {/* Встроенный каталог для плагина OrcaSlicer: обычный Layout (фон, модалки,
            вход) — хедер/футер он скрывает сам через isPluginEmbed(), навигация
            идёт с кнопок шелла плагина (postMessage → subscribeToPluginNavigation) */}
        <Route path="/embed" element={<Layout><CatalogPage /></Layout>} />
        <Route path="/embed/catalog" element={<Layout><CatalogPage /></Layout>} />
        <Route path="/about" element={<Layout><Suspense fallback={<PageLoader />}><AboutPage /></Suspense></Layout>} />
        <Route path="/user-agreement" element={<Suspense fallback={<PageLoader />}><TermsPage /></Suspense>} />
        <Route path="/privacy-policy" element={<Suspense fallback={<PageLoader />}><PrivacyPolicyPage /></Suspense>} />
        <Route path="/personal-data-consent" element={<Suspense fallback={<PageLoader />}><ConsentPage /></Suspense>} />
        <Route path="/reset-password" element={<Suspense fallback={<PageLoader />}><ResetPasswordPage /></Suspense>} />
        <Route path="/verify-email" element={<Suspense fallback={<PageLoader />}><VerifyEmailPage /></Suspense>} />
        <Route path="/confirm-email-change" element={<Suspense fallback={<PageLoader />}><ConfirmEmailChangePage /></Suspense>} />
        <Route path="/brand-invite/:token" element={<Suspense fallback={<PageLoader />}><BrandInvitePage /></Suspense>} />
        <Route path="/oauth/callback/:provider" element={<Suspense fallback={<PageLoader />}><OAuthCallbackPage /></Suspense>} />
        <Route path="/oauth/plugin-start/:provider" element={<Suspense fallback={<PageLoader />}><OAuthPluginStartPage /></Suspense>} />
        {DevUiKitPage && (
          <Route
            path="/dev/ui-kit"
            element={
              <Layout>
                <Suspense fallback={<PageLoader />}>
                  <DevUiKitPage />
                </Suspense>
              </Layout>
            }
          />
        )}
        <Route
          path="/quote/:uuid"
          element={
            <Layout>
              <Suspense fallback={<PageLoader />}>
                <SharedQuotePage />
              </Suspense>
            </Layout>
          }
        />
        <Route path="*" element={<Suspense fallback={<PageLoader />}><NotFoundPage /></Suspense>} />
      </Routes>
    </>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;
