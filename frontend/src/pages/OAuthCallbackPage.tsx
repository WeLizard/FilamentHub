/** OAuth callback page — receives code from provider and exchanges for JWT */

import { useEffect, useRef, useState } from 'react';
import { useSearchParams, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Loader2, AlertCircle } from 'lucide-react';
import { authAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { translateApiError } from '../utils/translateApiError';

export function OAuthCallbackPage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const { provider } = useParams<{ provider: string }>();
  const navigate = useNavigate();
  const { loginWithToken } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const calledRef = useRef(false);

  useEffect(() => {
    // Guard against React StrictMode double-invoke
    if (calledRef.current) return;
    calledRef.current = true;

    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const errorParam = searchParams.get('error');

    if (errorParam) {
      setError(t('oauthCallback.provider_denied', { provider: provider ?? '' }));
      return;
    }

    if (!code || !state || !provider) {
      setError(t('oauthCallback.missing_params'));
      return;
    }

    (async () => {
      try {
        const tokenData = await authAPI.oauthCallback(provider, code, state);
        await loginWithToken(tokenData.access_token, tokenData.refresh_token);
        navigate('/', { replace: true });
      } catch (err: any) {
        const detail = err?.response?.data?.detail;
        const fallback = t('oauthCallback.error_fallback', { provider: provider ?? '' });
        setError(translateApiError(t, detail, fallback));
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
          <button
            onClick={() => navigate('/', { replace: true })}
            className="mt-2 px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-colors text-sm"
          >
            {t('oauthCallback.back_home')}
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-10 h-10 text-purple-400 animate-spin" />
          <p className="text-gray-400 text-sm">{t('oauthCallback.signing_in')}</p>
        </div>
      )}
    </div>
  );
}
