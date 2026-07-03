/** Admin: calculator paid-access (paywall) / reverse-trial settings + subscription counts. */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles, Loader2 } from 'lucide-react';
import api from '../../api/client';
import { translateApiError } from '../../utils/translateApiError';

export function AdminSubscriptions() {
  const { t } = useTranslation();
  const [paywallEnforced, setPaywallEnforced] = useState(false);
  const [trialDays, setTrialDays] = useState<number | null>(null);
  const [counts, setCounts] = useState<{ trialing: number; active: number } | null>(null);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    load();
  }, []);

  const load = async () => {
    try {
      const response = await api.get('/admin/calculator-settings');
      setPaywallEnforced(Boolean(response.data.paywall_enforced));
      setTrialDays(response.data.trial_days ?? null);
      setCounts(response.data.counts ?? null);
    } catch (err) {
      console.error('Failed to load calculator settings:', err);
    }
  };

  const save = async (enforced: boolean, days: number | null) => {
    try {
      setUpdating(true);
      setError(null);
      const response = await api.post('/admin/calculator-settings', {
        paywall_enforced: enforced,
        trial_days: days,
      });
      setPaywallEnforced(Boolean(response.data.paywall_enforced));
      setTrialDays(response.data.trial_days ?? null);
      await load();
    } catch (err: any) {
      setError(translateApiError(t, err.response?.data?.detail, t('adminMaintenance.updateError')));
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="mb-2 flex items-center gap-3">
        <Sparkles className="h-6 w-6 text-cyan-400" />
        <h2 className="text-2xl font-bold text-white">{t('adminSubscriptions.title')}</h2>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-900/20 p-4 text-sm text-red-300">{error}</div>
      )}

      <div className="rounded-xl border border-white/10 bg-white/5 p-6">
        <h3 className="mb-4 text-lg font-semibold text-white">{t('adminMaintenance.calcTitle')}</h3>
        <div className="mb-4 flex items-center justify-between">
          <span className={`text-sm font-medium ${paywallEnforced ? 'text-yellow-300' : 'text-green-300'}`}>
            {paywallEnforced ? t('adminMaintenance.calcPaidOn') : t('adminMaintenance.calcPaidOff')}
          </span>
          <button
            onClick={() => save(!paywallEnforced, trialDays)}
            disabled={updating}
            className={`flex items-center gap-2 rounded-lg px-5 py-2.5 font-semibold transition-all disabled:opacity-50 ${
              paywallEnforced ? 'bg-green-600 text-white hover:bg-green-700' : 'bg-yellow-600 text-white hover:bg-yellow-700'
            }`}
          >
            {updating ? <Loader2 className="h-5 w-5 animate-spin" /> : null}
            <span>{paywallEnforced ? t('adminMaintenance.calcDisable') : t('adminMaintenance.calcEnable')}</span>
          </button>
        </div>
        <p className="mb-4 text-xs text-gray-500">
          {counts && (
            <span>{t('adminMaintenance.calcCounts', { trialing: counts.trialing, active: counts.active })} · </span>
          )}
          {t('adminMaintenance.calcAdminNote')}
        </p>
        <div className="flex items-center gap-3">
          <label className="text-sm text-gray-300">{t('adminMaintenance.calcTrial')}</label>
          <input
            type="number"
            min={0}
            value={trialDays ?? ''}
            onChange={(e) => setTrialDays(e.target.value === '' ? null : Math.max(0, Number(e.target.value)))}
            placeholder="∞"
            className="w-24 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <button
            onClick={() => save(paywallEnforced, trialDays)}
            disabled={updating}
            className="rounded-lg border border-white/20 bg-white/10 px-4 py-2 text-sm text-gray-200 hover:bg-white/20 disabled:opacity-50"
          >
            {t('adminMaintenance.calcSave')}
          </button>
        </div>
      </div>
    </div>
  );
}
