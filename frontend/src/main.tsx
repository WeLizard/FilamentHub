import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import './i18n';
import App from './App';
import './index.css';
import { clearLegacyLocalAuthStateIfNeeded } from './utils/auth';
import { stripOrcaHostTheme } from './utils/pluginBridge';
import { getLocaleBasename } from './utils/siteLocale';

clearLegacyLocalAuthStateIfNeeded();
stripOrcaHostTheme();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const localeBasename = getLocaleBasename(window.location.pathname);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={localeBasename}>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);

