import { Routes, Route, useNavigate, Link } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Layout } from './components/Layout';
import { CatalogPage } from './pages/CatalogPage';
import { ProfilePage } from './pages/ProfilePage';
import { FilamentDetailPage } from './pages/FilamentDetailPage';
import { BrandDetailPage } from './pages/BrandDetailPage';
import { AdminPanel } from './pages/AdminPanel';
import { TermsPage } from './pages/TermsPage';
import { ConsentPage } from './pages/ConsentPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { DownloadPage } from './pages/DownloadPage';
import { WikiPage } from './pages/WikiPage';
import { WikiCategoryPage } from './pages/WikiCategoryPage';
import { WikiArticlePage } from './pages/WikiArticlePage';
import { ToastContainer } from './components/Toast';
import { useOrcaSlicerNotifications } from './hooks/useOrcaSlicerNotifications';
import { useEffect } from 'react';
import { Notifications } from './components/Notifications';
import { useAuth } from './contexts/AuthContext';
import { MaintenancePage } from './components/MaintenancePage';

import { useTranslation } from 'react-i18next';

/** Страница 404 */
function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <Layout>
      <div style={{ padding: '3rem', textAlign: 'center' }}>
        <h1 style={{ fontSize: '3rem', marginBottom: '0.5rem' }}>404</h1>
        <p style={{ color: '#666', marginBottom: '1.5rem' }}>{t('notFound.title')}</p>
        <Link to="/" style={{ color: '#2563eb' }}>{t('notFound.goHome')}</Link>
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
              <BrandDetailPage />
            </Layout>
          }
        />
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <Layout>
                <ProfilePage />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedRoute requiredRole="admin">
              <AdminPanel />
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
              <WikiPage />
            </Layout>
          }
        />
        <Route
          path="/wiki/:slug"
          element={
            <Layout>
              <WikiCategoryPage />
            </Layout>
          }
        />
        <Route
          path="/wiki/articles/:slug"
          element={
            <Layout>
              <WikiArticlePage />
            </Layout>
          }
        />
        <Route path="/user-agreement" element={<TermsPage />} />
        <Route path="/personal-data-consent" element={<ConsentPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
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

