import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Eye } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useNavigate } from 'react-router-dom';

import { AuthContext, useAuth, type AuthContextType } from '../contexts/AuthContext';
import type { User } from '../types/api';
import {
  localizeDemoFixtures,
  rememberDemoChoice,
  startDemoSession,
  stopDemoSession,
  type DemoFixtures,
} from './demoTransport';

const DEMO_USER_KEY = '/auth/me';
const signInRequired = () => Promise.reject(new Error('Sign in to do this outside the demo'));

/**
 * Shows account screens to a guest with the recorded sample account.
 *
 * Children see a signed-in user through the usual auth context and load data
 * through the usual API client; the demo transport answers for the server. A
 * private query cache keeps sample data out of a real session that follows.
 */
export function DemoSession({ children }: { children: ReactNode }) {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage || i18n.language).split('-')[0];
  const account = useAuth();
  const navigate = useNavigate();
  const [fixtures, setFixtures] = useState<DemoFixtures | null>(null);
  const queryClient = useMemo(() => new QueryClient({
    defaultOptions: { queries: { refetchOnWindowFocus: false, retry: false, staleTime: Infinity } },
  }), []);

  useEffect(() => {
    let current = true;
    void Promise.all([import('./fixtures.json'), import('./texts.json')]).then(([recording, texts]) => {
      if (!current) return;
      const loaded = localizeDemoFixtures(recording.default as DemoFixtures, texts.default, locale);
      startDemoSession(loaded);
      rememberDemoChoice(true);
      setFixtures(loaded);
    });
    return () => {
      current = false;
      stopDemoSession();
      queryClient.clear();
    };
    // Switching the language restarts the session with the sample data in that language.
  }, [queryClient, locale]);

  const demoAuth = useMemo<AuthContextType | null>(() => {
    const user = fixtures?.responses[DEMO_USER_KEY] as User | undefined;
    if (!user) return null;
    return {
      user,
      isLoading: false,
      isAuthenticated: true,
      unauthenticatedReason: null,
      isMaintenanceMode: false,
      maintenanceMessage: null,
      login: signInRequired,
      loginWithToken: signInRequired,
      register: signInRequired,
      acceptLegalDocuments: signInRequired,
      logout: async () => {
        rememberDemoChoice(false);
        navigate('/');
      },
      refreshUser: async () => undefined,
      clearMaintenanceMode: () => undefined,
    };
  }, [fixtures, navigate]);

  // A person with an account has the real thing.
  if (account.isAuthenticated) {
    return <Navigate to="/profile" replace />;
  }
  if (account.isLoading || demoAuth === null) {
    return null;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={demoAuth}>
        <div
          role="status"
          className="relative z-20 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 border-b border-amber-300/30 bg-amber-400/10 px-4 py-2 text-sm text-amber-100"
        >
          <span className="inline-flex items-center gap-2">
            <Eye className="h-4 w-4 shrink-0" aria-hidden="true" />
            {t('demo.banner')}
          </span>
          <Link
            to="/?auth=login"
            onClick={() => rememberDemoChoice(false)}
            className="rounded-lg bg-purple-600 px-3 py-1 text-sm font-semibold text-white transition hover:bg-purple-500"
          >
            {t('demo.signUp')}
          </Link>
        </div>
        {children}
      </AuthContext.Provider>
    </QueryClientProvider>
  );
}
