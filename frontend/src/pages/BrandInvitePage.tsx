import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Loader, XCircle, Upload, Layers, QrCode, RefreshCw } from 'lucide-react';
import { brandInvitesAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { translateApiError } from '../utils/translateApiError';
import type { BrandInvitePublic } from '../types/api';

export function BrandInvitePage() {
  const { token = '' } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { user, refreshUser } = useAuth();

  const [invite, setInvite] = useState<BrandInvitePublic | null>(null);
  const [loading, setLoading] = useState(true);
  const [brandName, setBrandName] = useState('');
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    brandInvitesAPI
      .getByToken(token)
      .then((data) => {
        if (!active) return;
        setInvite(data);
        setBrandName(data.brand_name || '');
      })
      .catch(() => active && setInvite({ valid: false, brand_name: null, email: null, reason: null }))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [token]);

  const handleAccept = async () => {
    setError('');
    if (!brandName.trim()) {
      setError(t('brandInvite.errorName'));
      return;
    }
    setAccepting(true);
    try {
      await brandInvitesAPI.accept(token, brandName.trim());
      await refreshUser();
      navigate('/profile');
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setError(translateApiError(t, detail, t('brandInvite.errorGeneric')));
    } finally {
      setAccepting(false);
    }
  };

  const perks = [
    { icon: Layers, text: t('brandInvite.perkCatalog') },
    { icon: Upload, text: t('brandInvite.perkImport') },
    { icon: QrCode, text: t('brandInvite.perkQr') },
    { icon: RefreshCw, text: t('brandInvite.perkSync') },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-white/10 backdrop-blur-sm rounded-2xl border border-white/20 shadow-xl p-8">
        <img src="/logo.svg" alt="FilamentHub" className="w-14 h-14 object-contain mx-auto mb-4" />

        {loading ? (
          <div className="text-center">
            <Loader className="w-10 h-10 text-purple-400 animate-spin mx-auto mb-4" />
            <p className="text-gray-300">{t('brandInvite.loading')}</p>
          </div>
        ) : !invite?.valid ? (
          <div className="text-center">
            <XCircle className="w-14 h-14 text-red-400 mx-auto mb-4" />
            <h2 className="text-2xl font-bold text-white mb-2">{t('brandInvite.invalidTitle')}</h2>
            <p className="text-gray-300 mb-6">{t('brandInvite.invalidMessage')}</p>
            <Link
              to="/"
              className="inline-block px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all"
            >
              {t('brandInvite.toHome')}
            </Link>
          </div>
        ) : (
          <div>
            <h2 className="text-2xl font-bold text-white mb-2 text-center">{t('brandInvite.title')}</h2>
            <p className="text-gray-300 mb-5 text-center">{t('brandInvite.subtitle')}</p>

            <ul className="space-y-2 mb-6">
              {perks.map(({ icon: Icon, text }, i) => (
                <li key={i} className="flex items-center gap-3 text-gray-300 text-sm">
                  <span className="shrink-0 w-8 h-8 rounded-lg bg-purple-500/20 border border-purple-500/30 flex items-center justify-center">
                    <Icon className="w-4 h-4 text-purple-300" />
                  </span>
                  {text}
                </li>
              ))}
            </ul>

            {user ? (
              <>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('brandInvite.brandNameLabel')}</label>
                <input
                  type="text"
                  value={brandName}
                  onChange={(e) => setBrandName(e.target.value)}
                  maxLength={100}
                  placeholder={t('brandInvite.brandNamePlaceholder')}
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 mb-4"
                />
                {error && <p className="text-red-400 text-sm mb-3">{error}</p>}
                <button
                  type="button"
                  onClick={handleAccept}
                  disabled={accepting || !brandName.trim()}
                  className="w-full px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {accepting && <Loader className="w-4 h-4 animate-spin" />}
                  {t('brandInvite.accept')}
                </button>
              </>
            ) : (
              <div className="text-center">
                <p className="text-gray-300 mb-4">{t('brandInvite.loginPrompt')}</p>
                <Link
                  to="/"
                  className="inline-block px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all"
                >
                  {t('brandInvite.loginCta')}
                </Link>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
