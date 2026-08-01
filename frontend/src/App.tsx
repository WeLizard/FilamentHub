import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Layout } from './components/Layout';
import { CatalogPage } from './pages/CatalogPage';
import { FilamentDetailPage } from './pages/FilamentDetailPage';
import { TermsPage } from './pages/TermsPage';
import { ConsentPage } from './pages/ConsentPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { OAuthCallbackPage } from './pages/OAuthCallbackPage';
import { OAuthPluginStartPage } from './pages/OAuthPluginStartPage';
import { VerifyEmailPage } from './pages/VerifyEmailPage';
import { ConfirmEmailChangePage } from './pages/ConfirmEmailChangePage';
import { BrandInvitePage } from './pages/BrandInvitePage';
import { DownloadPage } from './pages/DownloadPage';
import { ToastContainer, toast } from './components/Toast';
import { useOrcaSlicerNotifications } from './hooks/useOrcaSlicerNotifications';
import { lazy, Suspense, useEffect, useState } from 'react';
import { isPluginEmbed, subscribeToPluginNavigation, subscribeToPluginSyncResult, subscribeToPluginRecoverList, sendRecoverImport, type RecoverItem } from './utils/pluginBridge';
import { Notifications } from './components/Notifications';
import { useAuth } from './contexts/AuthContext';
import { MaintenancePage } from './components/MaintenancePage';
import { NotFoundPage } from './pages/NotFoundPage';
import { RecoverPresetsModal } from './components/RecoverPresetsModal';
import { LegalOnboardingModal } from './components/LegalOnboardingModal';

// Lazy-loaded pages (code splitting)
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

// Prefetch all lazy chunks after initial page load so navigation feels instant
if (typeof window !== 'undefined') {
  window.addEventListener('load', () => {
    setTimeout(() => {
      import('./pages/ProfilePage');
      import('./pages/CalculatorPage');
      import('./pages/CrmWorkspacePage');
      import('./pages/BrandDetailPage');
      import('./pages/AdminPanel');
      import('./pages/WikiPage');
      import('./pages/WikiWorkspacePage');
      import('./pages/WikiCategoryPage');
      import('./pages/WikiArticlePage');
      import('./pages/PrivacyPolicyPage');
      import('./pages/FeedbackThreadPage');
      import('./components/CreatePresetModal');
      import('./components/CreatePrinterProfileModal');
    }, 2000);
  }, { once: true });
}

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
  const navigate = useNavigate();
  const location = useLocation();
  const { user, isMaintenanceMode, maintenanceMessage, clearMaintenanceMode } = useAuth();
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
    return subscribeToPluginSyncResult((text) => toast.success(text, undefined, 'sync'));
  }, []);

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
        <MaintenancePage 
          message={maintenanceMessage || undefined}
          onLoginSuccess={() => {
            // После успешного входа — обновляем состояние
            clearMaintenanceMode();
          }}
        />
      </>
    );
  }

  return (
    <>
      <ToastContainer />
      {user?.legal_onboarding_required && !onLegalPage && <LegalOnboardingModal />}
      {recoverItems && (
        <RecoverPresetsModal
          items={recoverItems}
          onClose={() => setRecoverItems(null)}
          onImport={(names) => {
            sendRecoverImport(names);
            setRecoverItems(null);
          }}
        />
      )}
      {/* Плавающая кнопка уведомлений для OrcaSlicer (когда нет хедера) */}
      {isInOrcaSlicer && user && <Notifications floating={true} />}
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
              <FilamentDetailPage />
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
              <DownloadPage />
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
        <Route path="/user-agreement" element={<TermsPage />} />
        <Route path="/privacy-policy" element={<Suspense fallback={<PageLoader />}><PrivacyPolicyPage /></Suspense>} />
        <Route path="/personal-data-consent" element={<ConsentPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/confirm-email-change" element={<ConfirmEmailChangePage />} />
        <Route path="/brand-invite/:token" element={<BrandInvitePage />} />
        <Route path="/oauth/callback/:provider" element={<OAuthCallbackPage />} />
        <Route path="/oauth/plugin-start/:provider" element={<OAuthPluginStartPage />} />
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
        <Route path="*" element={<NotFoundPage />} />
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
