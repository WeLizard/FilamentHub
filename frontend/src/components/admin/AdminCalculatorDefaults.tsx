/** Admin: platform defaults used only when a calculator profile is first created. */

import { useEffect, useState } from 'react';
import { Calculator, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { adminAPI } from '../../api/client';
import type { CalculatorProfileDefaults } from '../../types/api';
import { translateApiError } from '../../utils/translateApiError';

type NumericDefaultKey = Exclude<keyof CalculatorProfileDefaults, 'rounding_mode'>;

const DEFAULT_FIELD_GROUPS: Array<{
  titleKey: string;
  fields: Array<{ key: NumericDefaultKey; labelKey: string; step?: number }>;
}> = [
  {
    titleKey: 'adminCalculatorDefaults.rates',
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
    titleKey: 'adminCalculatorDefaults.commercial',
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
    titleKey: 'adminCalculatorDefaults.machine',
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

export function AdminCalculatorDefaults() {
  const { t } = useTranslation();
  const [profileDefaults, setProfileDefaults] = useState<CalculatorProfileDefaults | null>(null);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    adminAPI.getCalculatorSettings()
      .then((settings) => setProfileDefaults(settings.profile_defaults))
      .catch((err) => {
        console.error('Failed to load calculator profile defaults:', err);
        setError(t('adminCalculatorDefaults.loadError'));
      });
  }, [t]);

  const save = async () => {
    if (!profileDefaults) return;
    try {
      setUpdating(true);
      setError(null);
      setSaved(false);
      setProfileDefaults(await adminAPI.updateCalculatorProfileDefaults(profileDefaults));
      setSaved(true);
    } catch (err: any) {
      setError(translateApiError(t, err.response?.data?.detail, t('adminCalculatorDefaults.saveError')));
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3">
        <Calculator className="mt-0.5 h-6 w-6 text-cyan-400" />
        <div>
          <h2 className="text-2xl font-bold text-white">{t('adminCalculatorDefaults.title')}</h2>
          <p className="mt-1 max-w-4xl text-sm leading-6 text-slate-400">
            {t('adminCalculatorDefaults.description')}
          </p>
        </div>
      </div>

      {saved && (
        <div className="rounded-lg border border-emerald-400/25 bg-emerald-400/10 p-4 text-sm text-emerald-100">
          {t('adminCalculatorDefaults.saved')}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-900/20 p-4 text-sm text-red-300">{error}</div>
      )}

      <div className="rounded-xl border border-white/10 bg-white/5 p-6">
        {profileDefaults ? (
          <div className="space-y-6">
            {DEFAULT_FIELD_GROUPS.map((group) => (
              <section key={group.titleKey}>
                <h3 className="mb-3 text-sm font-semibold text-cyan-100">{t(group.titleKey)}</h3>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {group.fields.map((field) => (
                    <label key={field.key} className="block">
                      <span className="mb-1.5 block text-xs font-medium text-slate-400">{t(field.labelKey)}</span>
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
              <span className="mb-1.5 block text-xs font-medium text-slate-400">{t('profilePage.calc.roundingMode')}</span>
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
              <p className="max-w-3xl text-xs leading-5 text-slate-500">{t('adminCalculatorDefaults.existingUsers')}</p>
              <button
                type="button"
                onClick={save}
                disabled={updating}
                className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:opacity-50"
              >
                {updating ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {t('adminCalculatorDefaults.save')}
              </button>
            </div>
          </div>
        ) : !error ? (
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('common.loading')}
          </div>
        ) : null}
      </div>
    </div>
  );
}
