import { useState } from 'react';
import { BookOpen, LogOut, Package, RefreshCw, RotateCcw, User } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import {
  requestPluginDiagnostics,
  requestPluginProfileSync,
  requestPluginRecovery,
} from '../utils/pluginBridge';

interface OrcaPluginToolbarProps {
  authenticated: boolean;
  accountLabel: string | null;
  showDiagnostics: boolean;
  onLogin: () => void;
  onLogout: () => void;
}

export function OrcaPluginToolbar({
  authenticated,
  accountLabel,
  showDiagnostics,
  onLogin,
  onLogout,
}: OrcaPluginToolbarProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [syncing, setSyncing] = useState(false);

  const destinations = [
    { path: '/', label: t('layout.nav_catalog'), icon: Package, authenticated: false },
    { path: '/profile', label: t('layout.nav_profile'), icon: User, authenticated: true },
    { path: '/wiki', label: t('layout.nav_wiki'), icon: BookOpen, authenticated: false },
  ];

  const navigateInsidePlugin = (path: string) => {
    // Keep the per-tab bridge binding in the URL. A hard reload on Profile or
    // Wiki must reopen the same direct plugin surface instead of site chrome.
    navigate({ pathname: path, hash: location.hash });
  };

  const runSync = async () => {
    if (syncing) return;
    setSyncing(true);
    try {
      await requestPluginProfileSync('all');
    } catch {
      // The shared plugin result subscriber shows the host-provided error.
    } finally {
      setSyncing(false);
    }
  };

  const buttonClass = (active = false) => [
    'inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors',
    active
      ? 'border-purple-400/70 bg-purple-500/20 text-white'
      : 'border-transparent text-gray-200 hover:border-white/20 hover:bg-white/10',
  ].join(' ');

  return (
    <header
      data-testid="orca-plugin-toolbar"
      className="sticky top-0 z-[90] border-b border-white/10 bg-slate-950/95 px-3 py-2 shadow-lg backdrop-blur"
    >
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        <div data-testid="orca-plugin-account-group" className="mr-auto flex min-w-0 items-center gap-1.5">
          <button
            type="button"
            onClick={authenticated ? undefined : onLogin}
            disabled={authenticated}
            className="inline-flex min-h-9 min-w-0 items-center rounded-md border border-white/15 px-3 py-1.5 text-sm font-semibold text-white disabled:cursor-default disabled:border-transparent"
          >
            <span className="truncate">{accountLabel || t('layout.nav_login')}</span>
          </button>

          {authenticated && (
            <button type="button" onClick={onLogout} className={buttonClass()}>
              <LogOut className="h-4 w-4" />
              {t('layout.nav_logout')}
            </button>
          )}
        </div>

        {destinations
          .filter((item) => !item.authenticated || authenticated)
          .map(({ path, label, icon: Icon }) => (
            <button
              key={path}
              type="button"
              onClick={() => navigateInsidePlugin(path)}
              className={buttonClass(location.pathname === path)}
              aria-current={location.pathname === path ? 'page' : undefined}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}

        {authenticated && (
          <>
            <button type="button" onClick={() => void runSync()} disabled={syncing} className={buttonClass()}>
              <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
              {t('layout.plugin_sync')}
            </button>
            <button type="button" onClick={requestPluginRecovery} className={buttonClass()}>
              <RotateCcw className="h-4 w-4" />
              {t('layout.plugin_recover')}
            </button>
          </>
        )}

        {showDiagnostics && (
          <button type="button" onClick={requestPluginDiagnostics} className={buttonClass()}>
            {t('layout.plugin_log')}
          </button>
        )}
      </div>
    </header>
  );
}
