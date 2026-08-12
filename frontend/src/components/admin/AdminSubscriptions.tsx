/** Admin: calculator paid-access (paywall) / reverse-trial settings + subscription counts. */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles, Loader2 } from 'lucide-react';
import { adminAPI } from '../../api/client';
import { translateApiError } from '../../utils/translateApiError';
import type { CalculatorProfileDefaults } from '../../types/api';

type NumericDefaultKey = Exclude<keyof CalculatorProfileDefaults, 'rounding_mode'>;

const DEFAULT_FIELD_GROUPS: Array<{
  titleKey: string;
  fields: Array<{ key: NumericDefaultKey; labelKey: string; step?: number }>;
}> = [
  {
    titleKey: 'adminSubscriptions.defaultsRates',
    fields: [
      { key: 'electricity_cost_per_kwh', labelKey: 'profilePage.calc.electricityCost', step: 0.01 },
      { key: 'modeling_rate_per_hour', labelKey: 'profilePage.calc.modeling', step: 0.01 },
      { key: 'postprocessing_rate_per_hour', labelKey: 'profilePage.calc.postprocessing', step: 0.01 },
      { key: 'printing_rate_per_hour', labelKey: 'profilePage.calc.printingRate', step: 0.01 },
      { key: 'amortization_rate_per_hour', labelKey: 'profilePage.calc.amortizationRate', step: 0.01 },
      { key: 'maintenance_cost_per_hour', labelKey: 'printerEconomics.maintenanceField', step: 0.01 },
    ],
  },
  {
    titleKey: 'adminSubscriptions.defaultsCommercial',
    fields: [
      { key: 'overhead_percent', labelKey: 'profilePage.calc.overheadPercent', step: 0.1 },
      { key: 'markup_percent', labelKey: 'profilePage.calc.markupPercent', step: 0.1 },
      { key: 'tax_rate_percent', labelKey: 'profilePage.calc.taxRatePercent', step: 0.1 },
      { key: 'fixed_costs', labelKey: 'profilePage.calc.fixedCosts', step: 0.01 },
      { key: 'bed_prep_cost_per_print', labelKey: 'profilePage.calc.bedPrepCost', step: 0.01 },
      { key: 'min_order_price', labelKey: 'profilePage.calc.minOrderPrice', step: 0.01 },
      { key: 'round_to_nearest', labelKey: 'profilePage.calc.roundTo', step: 1 },
    ],
  },
  {
    titleKey: 'adminSubscriptions.defaultsMachine',
    fields: [
      { key: 'printer_power_w', labelKey: 'profilePage.calc.printerPower', step: 1 },
      { key: 'printer_purchase_price', labelKey: 'profilePage.calculator.printerPurchasePrice', step: 0.01 },
      { key: 'printer_useful_hours', labelKey: 'profilePage.calculator.printerUsefulHours', step: 1 },
      { key: 'power_hotend_w', labelKey: 'profilePage.calculator.powerHotend', step: 1 },
      { key: 'power_bed_w', labelKey: 'profilePage.calculator.powerBed', step: 1 },
      { key: 'power_steppers_w', labelKey: 'profilePage.calculator.powerSteppers', step: 1 },
      { key: 'power_electronics_w', labelKey: 'profilePage.calculator.powerElectronics', step: 1 },
    ],
  },
];

export function AdminSubscriptions() {
  const { t } = useTranslation();
  const [paywallEnforced, setPaywallEnforced] = useState(false);
  const [trialDays, setTrialDays] = useState<number | null>(null);
  const [counts, setCounts] = useState<{ trialing: number; active: number } | null>(null);
  const [profileDefaults, setProfileDefaults] = useState<CalculatorProfileDefaults | null>(null);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    load();
  }, []);

  const load = async () => {
    try {
      const settings = await adminAPI.getCalculatorSettings();
      setPaywallEnforced(Boolean(settings.paywall_enforced));
      setTrialDays(settings.trial_days ?? null);
      setCounts(settings.counts ?? null);
      setProfileDefaults(settings.profile_defaults);
    } catch (err) {
      console.error('Failed to load calculator settings:', err);
    }
  };

  const save = async (
    enforced: boolean,
    days: number | null,
    defaults?: CalculatorProfileDefaults,
  ) => {
    try {
      setUpdating(true);
      setError(null);
      setSaved(false);
      const settings = await adminAPI.updateCalculatorSettings(enforced, days, defaults);
      setPaywallEnforced(Boolean(settings.paywall_enforced));
      setTrialDays(settings.trial_days ?? null);
      setProfileDefaults(settings.profile_defaults);
      setSaved(true);
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

      {saved && (
        <div className="rounded-lg border border-emerald-400/25 bg-emerald-400/10 p-4 text-sm text-emerald-100">
          {t('adminSubscriptions.saved')}
        </div>
      )}

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

      <div className="rounded-xl border border-white/10 bg-white/5 p-6">
        <h3 className="text-lg font-semibold text-white">{t('adminSubscriptions.defaultsTitle')}</h3>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">
          {t('adminSubscriptions.defaultsDescription')}
        </p>

        {profileDefaults ? (
          <div className="mt-6 space-y-6">
            {DEFAULT_FIELD_GROUPS.map((group) => (
              <section key={group.titleKey}>
                <h4 className="mb-3 text-sm font-semibold text-cyan-100">{t(group.titleKey)}</h4>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {group.fields.map((field) => (
                    <label key={field.key} className="block">
                      <span className="mb-1.5 block text-xs font-medium text-slate-400">
                        {t(field.labelKey)}
                      </span>
                      <input
                        type="number"
                        min={0}
                        step={field.step ?? 0.01}
                        value={profileDefaults[field.key]}
                        onChange={(event) => {
                          const value = Number(event.target.value);
                          setProfileDefaults((current) => current
                            ? { ...current, [field.key]: Number.isFinite(value) ? Math.max(0, value) : 0 }
                            : current);
                        }}
                        className="w-full rounded-lg border border-white/10 bg-slate-950/45 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                      />
                    </label>
                  ))}
                </div>
              </section>
            ))}

            <label className="block max-w-sm">
              <span className="mb-1.5 block text-xs font-medium text-slate-400">
                {t('profilePage.calc.roundingMode')}
              </span>
              <select
                value={profileDefaults.rounding_mode}
                onChange={(event) => setProfileDefaults((current) => current
                  ? { ...current, rounding_mode: event.target.value as CalculatorProfileDefaults['rounding_mode'] }
                  : current)}
                className="w-full rounded-lg border border-white/10 bg-slate-950/45 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                <option value="up">{t('profilePage.calc.roundingModeUp')}</option>
                <option value="nearest">{t('profilePage.calc.roundingModeNearest')}</option>
                <option value="down">{t('profilePage.calc.roundingModeDown')}</option>
              </select>
            </label>

            <div className="flex flex-col gap-3 border-t border-white/10 pt-5 sm:flex-row sm:items-center sm:justify-between">
              <p className="max-w-3xl text-xs leading-5 text-slate-500">
                {t('adminSubscriptions.defaultsExistingUsers')}
              </p>
              <button
                type="button"
                onClick={() => save(paywallEnforced, trialDays, profileDefaults)}
                disabled={updating}
                className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:opacity-50"
              >
                {updating ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {t('adminSubscriptions.saveDefaults')}
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-6 flex items-center gap-2 text-sm text-slate-400">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('common.loading')}
          </div>
        )}
      </div>
    </div>
  );
}
