import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import './i18n';
import App from './App';
import './index.css';
import { clearLegacyLocalAuthStateIfNeeded } from './utils/auth';
import { stripOrcaHostTheme } from './utils/pluginBridge';

const favicon = document.querySelector<HTMLLinkElement>('#theme-favicon');
const rasterFavicon = document.querySelector<HTMLLinkElement>('#theme-favicon-raster');
const darkColorScheme = window.matchMedia?.('(prefers-color-scheme: dark)');

if ((favicon || rasterFavicon) && darkColorScheme) {
  const updateFavicon = () => {
    if (favicon) {
      favicon.href = darkColorScheme.matches ? '/favicon-dark.svg' : '/favicon.svg';
    }
    if (rasterFavicon) {
      rasterFavicon.href = darkColorScheme.matches ? '/favicon-dark-120.png' : '/favicon-120.png';
    }
  };

  updateFavicon();
  darkColorScheme.addEventListener('change', updateFavicon);
}

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

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);

