import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { i18nReady } from './i18n';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { StartupReady, reportStartupFailure } from './components/StartupReady';
import './index.css';
import './pluginAppearance.css';
import { clearLegacyLocalAuthStateIfNeeded } from './utils/auth';
import { isPluginEmbed, stripOrcaHostTheme } from './utils/pluginBridge';
import { initializePluginAppearance } from './utils/pluginAppearance';
import { getLocaleBasename } from './utils/siteLocale';

async function startApp(): Promise<void> {
  try {
    clearLegacyLocalAuthStateIfNeeded();
    stripOrcaHostTheme();
    initializePluginAppearance(isPluginEmbed());

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          refetchOnWindowFocus: false,
          retry: 1,
          staleTime: 30_000,
        },
      },
    });
    const localeBasename = getLocaleBasename(window.location.pathname);
    const homeHref = localeBasename ? `${localeBasename}/` : '/';

    await i18nReady;
    ReactDOM.createRoot(document.getElementById('root')!).render(
      <React.StrictMode>
        <QueryClientProvider client={queryClient}>
          <StartupReady>
            <ErrorBoundary homeHref={homeHref}>
              <BrowserRouter basename={localeBasename}>
                <App />
              </BrowserRouter>
            </ErrorBoundary>
          </StartupReady>
        </QueryClientProvider>
      </React.StrictMode>,
    );
  } catch (error) {
    reportStartupFailure();
    // Preserve the original browser diagnostic, including on ordinary routes
    // where the embed-only watchdog is intentionally inactive.
    throw error;
  }
}

void startApp();

