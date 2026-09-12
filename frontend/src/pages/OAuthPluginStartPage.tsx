/**
 * OAuth entry point for the OrcaSlicer plugin, opened in the user's real browser.
 *
 * The plugin can't run provider consent inside its embedded WebView, so
 * The embedded SPA first creates a server-backed one-time handoff, then asks
 * the host to open its browser URL here. The high-entropy flow ID stays in this tab's sessionStorage while
 * the provider flow runs; account tokens are delivered only to the plugin's
 * separate polling secret and never appear in a browser URL.
 */

import { useEffect, useRef, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Loader2, AlertCircle } from 'lucide-react';
import { authAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import {
  clearPluginOAuthHandoff,
  rememberPluginOAuthHandoff,
} from '../utils/pluginBridge';

const VALID_PROVIDERS = new Set(['google', 'yandex']);

export function OAuthPluginStartPage() {
  const { t } = useTranslation();
  const { provider } = useParams<{ provider: string }>();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    const flowId = searchParams.get('flow') || '';
    window.history.replaceState(window.history.state, '', window.location.pathname);

    if (
      !provider
      || !VALID_PROVIDERS.has(provider)
      || !rememberPluginOAuthHandoff(flowId)
    ) {
      setError(t('pluginOAuth.startError'));
      return;
    }

    (async () => {
      try {
        const { url } = await authAPI.authorizePluginOAuthFlow(
          flowId,
          provider as 'google' | 'yandex',
        );
        window.location.href = url;
      } catch (err: any) {
        clearPluginOAuthHandoff();
        const detail = err?.response?.data?.detail;
        setError(translateApiError(t, detail, t('pluginOAuth.startError')));
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      {error ? (
        <div className="flex flex-col items-center gap-4 text-center max-w-sm px-4">
          <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center">
            <AlertCircle className="w-8 h-8 text-red-400" />
          </div>
          <p className="text-white font-semibold">{t('oauthCallback.error_title')}</p>
          <p className="text-gray-400 text-sm">{error}</p>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-10 h-10 text-purple-400 animate-spin" />
          <p className="text-gray-400 text-sm">{t('pluginOAuth.startRedirecting')}</p>
        </div>
      )}
    </div>
  );
}
