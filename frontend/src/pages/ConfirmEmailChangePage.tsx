/** Страница подтверждения смены email */

import { useEffect, useRef, useState } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { CheckCircle, XCircle, Loader } from 'lucide-react';
import { authAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';

export function ConfirmEmailChangePage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const calledRef = useRef(false);

  const [state, setState] = useState<'loading' | 'success' | 'error'>('loading');
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    if (calledRef.current) return;
    calledRef.current = true;

    const token = searchParams.get('token');
    if (!token) {
      navigate('/');
      return;
    }

    authAPI.confirmEmailChange(token)
      .then(() => setState('success'))
      .catch((err: any) => {
        const detail = err.response?.data?.detail;
        setErrorMessage(translateApiError(t, detail, t('confirmEmailChange.errorFallback')));
        setState('error');
      });
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white/10 backdrop-blur-sm rounded-2xl border border-white/20 shadow-xl p-8 text-center">
        <img src="/logo.svg" alt="FilamentHub" className="w-14 h-14 object-contain mx-auto mb-4" />

        {state === 'loading' && (
          <>
            <Loader className="w-10 h-10 text-purple-400 animate-spin mx-auto mb-4" />
            <p className="text-gray-300">{t('confirmEmailChange.loading')}</p>
          </>
        )}

        {state === 'success' && (
          <>
            <CheckCircle className="w-14 h-14 text-green-400 mx-auto mb-4" />
            <h2 className="text-2xl font-bold text-white mb-2">{t('confirmEmailChange.successTitle')}</h2>
            <p className="text-gray-300 mb-6">{t('confirmEmailChange.successMessage')}</p>
            <Link
              to="/"
              className="inline-block px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all"
            >
              {t('confirmEmailChange.goHome')}
            </Link>
          </>
        )}

        {state === 'error' && (
          <>
            <XCircle className="w-14 h-14 text-red-400 mx-auto mb-4" />
            <h2 className="text-2xl font-bold text-white mb-2">{t('confirmEmailChange.errorTitle')}</h2>
            <p className="text-gray-300 mb-6">{errorMessage}</p>
            <Link
              to="/"
              className="inline-block px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all border border-white/20"
            >
              {t('confirmEmailChange.goHome')}
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
