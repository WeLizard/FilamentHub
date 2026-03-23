import { Routes, Route, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Home, SearchX, Loader2 } from 'lucide-react';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Layout } from './components/Layout';
import { CatalogPage } from './pages/CatalogPage';
import { FilamentDetailPage } from './pages/FilamentDetailPage';
import { TermsPage } from './pages/TermsPage';
import { ConsentPage } from './pages/ConsentPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { OAuthCallbackPage } from './pages/OAuthCallbackPage';
import { ConfirmEmailChangePage } from './pages/ConfirmEmailChangePage';
import { DownloadPage } from './pages/DownloadPage';
import { ToastContainer } from './components/Toast';
import { useOrcaSlicerNotifications } from './hooks/useOrcaSlicerNotifications';
import { lazy, Suspense, useEffect } from 'react';
import { Notifications } from './components/Notifications';
import { useAuth } from './contexts/AuthContext';
import { MaintenancePage } from './components/MaintenancePage';

import { useTranslation } from 'react-i18next';

// Lazy-loaded pages (code splitting)
const ProfilePage = lazy(() => import('./pages/ProfilePage').then(m => ({ default: m.ProfilePage })));
const CalculatorPage = lazy(() => import('./pages/CalculatorPage').then(m => ({ default: m.CalculatorPage })));
const BrandDetailPage = lazy(() => import('./pages/BrandDetailPage').then(m => ({ default: m.BrandDetailPage })));
const AdminPanel = lazy(() => import('./pages/AdminPanel').then(m => ({ default: m.AdminPanel })));
const WikiPage = lazy(() => import('./pages/WikiPage').then(m => ({ default: m.WikiPage })));
const WikiCategoryPage = lazy(() => import('./pages/WikiCategoryPage').then(m => ({ default: m.WikiCategoryPage })));
const WikiArticlePage = lazy(() => import('./pages/WikiArticlePage').then(m => ({ default: m.WikiArticlePage })));

// Prefetch all lazy chunks after initial page load so navigation feels instant
if (typeof window !== 'undefined') {
  window.addEventListener('load', () => {
    setTimeout(() => {
      import('./pages/ProfilePage');
      import('./pages/CalculatorPage');
      import('./pages/BrandDetailPage');
      import('./pages/AdminPanel');
      import('./pages/WikiPage');
      import('./pages/WikiCategoryPage');
      import('./pages/WikiArticlePage');
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

/** Страница 404 */
function NotFoundPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const handleGoBack = () => {
    if (window.history.length > 1) {
      navigate(-1);
      return;
    }

    navigate('/');
  };

  return (
    <Layout>
      <div className="relative z-10 mx-auto flex min-h-[70vh] w-full max-w-4xl items-center justify-center px-4 py-12 sm:px-6">
        <div className="w-full rounded-3xl border border-white/10 bg-black/30 p-8 shadow-2xl shadow-black/30 backdrop-blur-md sm:p-12">
          <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl bg-purple-500/20 ring-1 ring-purple-400/40">
            <SearchX className="h-10 w-10 text-purple-300" />
          </div>

          <p className="text-center text-sm font-semibold uppercase tracking-[0.24em] text-purple-300">404</p>
          <h1 className="mt-3 text-center text-3xl font-bold text-white sm:text-4xl">{t('notFound.title')}</h1>
          <p className="mx-auto mt-4 max-w-xl text-center text-sm text-gray-300 sm:text-base">
            {t('notFound.subtitle')}
          </p>

          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              to="/"
              className="inline-flex min-w-[220px] items-center justify-center gap-2 rounded-xl bg-purple-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-purple-500"
            >
              <Home className="h-4 w-4" />
              {t('notFound.goHome')}
            </Link>

            <button
              type="button"
              onClick={handleGoBack}
              className="inline-flex min-w-[220px] items-center justify-center gap-2 rounded-xl border border-white/20 bg-white/5 px-5 py-3 text-sm font-semibold text-gray-200 transition hover:bg-white/10"
            >
              <ArrowLeft className="h-4 w-4" />
              {t('notFound.goBack')}
            </button>
          </div>
        </div>
      </div>
    </Layout>
  );
}

// ... (AppContent and App)


function AppContent() {
  // Обработчик уведомлений от OrcaSlicer
  useOrcaSlicerNotifications();
  const navigate = useNavigate();
  const { user, isMaintenanceMode, maintenanceMessage, clearMaintenanceMode } = useAuth();
  
  // Проверяем, запущен ли frontend внутри OrcaSlicer
  const isInOrcaSlicer = typeof window !== 'undefined' && (
    (window as any).filamenthub?.importProfile ||
    (window as any).wx?.postMessage
  );
  
  // Добавляем глобальную функцию для навигации из OrcaSlicer без перезагрузки страницы
  useEffect(() => {
    if (typeof window !== 'undefined') {
      // Создаём объект filamenthub если его нет
      if (!(window as any).filamenthub) {
        (window as any).filamenthub = {};
      }

      // Добавляем функцию навигации
      (window as any).filamenthub.navigate = (path: string) => {
        navigate(path);
      };
    }
  }, [navigate]);

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
          path="/brands/:id"
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
        <Route path="/user-agreement" element={<TermsPage />} />
        <Route path="/personal-data-consent" element={<ConsentPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/confirm-email-change" element={<ConfirmEmailChangePage />} />
        <Route path="/oauth/callback/:provider" element={<OAuthCallbackPage />} />
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
