import { useEffect, useRef, useState } from 'react';
import { BookOpen, Bug, LogOut, Package, RefreshCw, RotateCcw, User } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import {
  requestPluginProfileSync,
  requestPluginRecovery,
} from '../utils/pluginBridge';
import { openProblemReport } from '../utils/problemReport';
import { usePluginDeveloperMode } from '../hooks/usePluginDeveloperMode';

interface OrcaPluginToolbarProps {
  authenticated: boolean;
  accountLabel: string | null;
  onLogin: () => void;
  onLogout: () => void;
}

const TOOLBAR_HEIGHT_PROPERTY = '--orca-plugin-toolbar-height';

export function OrcaPluginToolbar({
  authenticated,
  accountLabel,
  onLogin,
  onLogout,
}: OrcaPluginToolbarProps) {
  const { t } = useTranslation();
  const developerMode = usePluginDeveloperMode();
  const navigate = useNavigate();
  const location = useLocation();
  const [syncing, setSyncing] = useState(false);
  const toolbarRef = useRef<HTMLElement>(null);

  // Toasts are positioned below the toolbar instead of over its controls; the
  // toolbar wraps on narrow Orca panels, so its height is measured, not fixed.
  useEffect(() => {
    const toolbar = toolbarRef.current;
    if (!toolbar) return undefined;
    const root = document.documentElement;
    const publish = () => {
      root.style.setProperty(TOOLBAR_HEIGHT_PROPERTY, `${toolbar.offsetHeight}px`);
    };
    publish();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(publish);
    observer?.observe(toolbar);
    return () => {
      observer?.disconnect();
      root.style.removeProperty(TOOLBAR_HEIGHT_PROPERTY);
    };
  }, []);

  const destinations = [
    {
      path: '/embed',
      search: '?tab=spools',
      label: t('layout.plugin_nav_spools'),
      icon: Package,
      authenticated: true,
    },
    {
      path: '/embed/catalog',
      search: '',
      label: t('layout.nav_catalog'),
      icon: Package,
      authenticated: false,
    },
    {
      path: '/profile',
      search: '?tab=dashboard',
      label: t('layout.nav_profile'),
      icon: User,
      authenticated: true,
    },
    { path: '/wiki', search: '', label: t('layout.nav_wiki'), icon: BookOpen, authenticated: false },
  ];

  const navigateInsidePlugin = (path: string, search: string) => {
    // Keep the per-tab bridge binding in the URL. A hard reload on Profile or
    // Wiki must reopen the same direct plugin surface instead of site chrome.
    const nextParams = new URLSearchParams(search);
    const hostLanguage = new URLSearchParams(location.search).get('lng');
    if (hostLanguage && !nextParams.has('lng')) {
      nextParams.set('lng', hostLanguage);
    }
    const nextSearch = nextParams.toString();
    navigate({
      pathname: path,
      search: nextSearch ? `?${nextSearch}` : '',
      hash: location.hash,
    });
  };

  const isActiveDestination = (path: string) => {
    if (path === '/embed') {
      return location.pathname === '/embed';
    }
    if (location.pathname !== path) return false;
    return true;
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
      ref={toolbarRef}
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
          .map(({ path, search, label, icon: Icon }) => {
            const active = isActiveDestination(path);
            return (
              <button
                key={`${path}${search}`}
                type="button"
                onClick={() => navigateInsidePlugin(path, search)}
                className={buttonClass(active)}
                aria-current={active ? 'page' : undefined}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            );
          })}

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
            {developerMode && (
              <button
                type="button"
                onClick={() => openProblemReport()}
                className={buttonClass()}
                title={t('layout.plugin_report_problem')}
                aria-label={t('layout.plugin_report_problem')}
              >
                <Bug className="h-4 w-4" />
              </button>
            )}
          </>
        )}
      </div>
    </header>
  );
}
