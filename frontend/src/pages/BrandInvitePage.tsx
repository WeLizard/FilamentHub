import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Building2, Loader, XCircle, Upload, Layers, QrCode, RefreshCw } from 'lucide-react';
import { brandInvitesAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { AuthModal } from '../components/AuthModal';
import { translateApiError } from '../utils/translateApiError';
import type { BrandInvitePublic } from '../types/api';

export function BrandInvitePage() {
  const { token = '' } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { user, refreshUser } = useAuth();

  const [invite, setInvite] = useState<BrandInvitePublic | null>(null);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState('');
  const [authOpen, setAuthOpen] = useState(false);

  useEffect(() => {
    let active = true;
    brandInvitesAPI
      .getByToken(token)
      .then((data) => {
        if (!active) return;
        setInvite(data);
      })
      .catch(() => active && setInvite({
        valid: false,
        brand_name: null,
        email: null,
        target_type: null,
        brand_id: null,
        reason: null,
      }))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [token]);

  const handleAccept = async () => {
    setError('');
    setAccepting(true);
    try {
      await brandInvitesAPI.accept(token);
      await refreshUser();
      navigate('/profile', { state: { brandCabinet: true, editBrand: true } });
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

            <div className="mb-6 rounded-xl border border-purple-400/25 bg-purple-400/10 px-4 py-3">
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-purple-400/15 text-purple-200">
                  <Building2 className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <p className="text-xs uppercase tracking-[0.16em] text-purple-200/70">
                    {t('brandInvite.invitedBrand')}
                  </p>
                  <p className="truncate text-lg font-semibold text-white">{invite.brand_name}</p>
                </div>
              </div>
              {invite.email && (
                <p className="mt-3 text-xs leading-5 text-gray-400">
                  {t('brandInvite.emailHint', { email: invite.email })}
                </p>
              )}
            </div>

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
                {error && <p className="text-red-400 text-sm mb-3">{error}</p>}
                <button
                  type="button"
                  onClick={handleAccept}
                  disabled={accepting}
                  className="w-full px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {accepting && <Loader className="w-4 h-4 animate-spin" />}
                  {t('brandInvite.accept')}
                </button>
              </>
            ) : (
              <div className="text-center">
                <p className="text-gray-300 mb-4">{t('brandInvite.loginPrompt')}</p>
                <button
                  type="button"
                  onClick={() => setAuthOpen(true)}
                  className="inline-block px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all"
                >
                  {t('brandInvite.loginCta')}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
      <AuthModal isOpen={authOpen} onClose={() => setAuthOpen(false)} initialMode="register" />
    </div>
  );
}
