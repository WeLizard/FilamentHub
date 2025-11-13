import { Routes, Route, useNavigate } from 'react-router-dom';
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
import { ToastContainer } from './components/Toast';
import { useOrcaSlicerNotifications } from './hooks/useOrcaSlicerNotifications';
import { useEffect } from 'react';

function AppContent() {
  // Обработчик уведомлений от OrcaSlicer
  useOrcaSlicerNotifications();
  const navigate = useNavigate();
  
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

  return (
    <>
      <ToastContainer />
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
        <Route path="/user-agreement" element={<TermsPage />} />
        <Route path="/personal-data-consent" element={<ConsentPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
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

