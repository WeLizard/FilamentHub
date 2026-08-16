/** Admin: platform defaults used only when a calculator profile is first created. */

import { useEffect, useState } from 'react';
import { Calculator, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { adminAPI } from '../../api/client';
import { currencySymbol } from '../../utils/currency';
import type { CalculatorProfileDefaults } from '../../types/api';
import { translateApiError } from '../../utils/translateApiError';

type NumericDefaultKey = Exclude<keyof CalculatorProfileDefaults, 'rounding_mode' | 'currency'>;

const DEFAULTS_CURRENCIES = ['RUB', 'USD', 'EUR', 'CNY'] as const;

type FieldUnit = 'money' | 'moneyPerHour' | 'moneyPerKwh' | 'percent' | 'watt' | 'hour';

// Same grouping as the person sees in their own economics, so a value means the same
// thing on both screens and the admin is not guessing which field feeds what.
const DEFAULT_FIELD_GROUPS: Array<{
  titleKey: string;
  fields: Array<{ key: NumericDefaultKey; labelKey: string; step?: number; unit: FieldUnit }>;
}> = [
  {
    titleKey: 'adminCalculatorDefaults.perHour',
    fields: [
      { key: 'electricity_cost_per_kwh', labelKey: 'profilePage.calc.electricityCost', step: 0.01, unit: 'moneyPerKwh' },
      { key: 'modeling_rate_per_hour', labelKey: 'profilePage.calc.modeling', step: 0.01, unit: 'moneyPerHour' },
      { key: 'postprocessing_rate_per_hour', labelKey: 'profilePage.calc.postprocessing', step: 0.01, unit: 'moneyPerHour' },
      { key: 'printing_rate_per_hour', labelKey: 'profilePage.calc.printingRate', step: 0.01, unit: 'moneyPerHour' },
      { key: 'amortization_rate_per_hour', labelKey: 'profilePage.calc.amortizationRate', step: 0.01, unit: 'moneyPerHour' },
      { key: 'maintenance_cost_per_hour', labelKey: 'printerCost.maintenanceLine', step: 0.01, unit: 'moneyPerHour' },
    ],
  },
  {
    titleKey: 'adminCalculatorDefaults.perOrder',
    fields: [
      { key: 'bed_prep_cost_per_print', labelKey: 'profilePage.calc.bedPrepCost', step: 0.01, unit: 'money' },
      { key: 'fixed_costs', labelKey: 'profilePage.calc.fixedCosts', step: 0.01, unit: 'money' },
      { key: 'min_order_price', labelKey: 'profilePage.calc.minOrderPrice', step: 0.01, unit: 'money' },
    ],
  },
  {
    titleKey: 'adminCalculatorDefaults.markupAndTax',
    fields: [
      { key: 'overhead_percent', labelKey: 'profilePage.calc.overheadPercent', step: 0.1, unit: 'percent' },
      { key: 'markup_percent', labelKey: 'profilePage.calc.markupPercent', step: 0.1, unit: 'percent' },
      { key: 'tax_rate_percent', labelKey: 'profilePage.calc.taxRatePercent', step: 0.1, unit: 'percent' },
    ],
  },
  {
    titleKey: 'adminCalculatorDefaults.finalPrice',
    fields: [
      { key: 'round_to_nearest', labelKey: 'profilePage.calc.roundTo', step: 1, unit: 'money' },
    ],
  },
  {
    titleKey: 'adminCalculatorDefaults.machine',
    fields: [
      { key: 'printer_purchase_price', labelKey: 'profilePage.calculator.printerPurchasePrice', step: 0.01, unit: 'money' },
      { key: 'printer_useful_hours', labelKey: 'profilePage.calculator.printerUsefulHours', step: 1, unit: 'hour' },
      { key: 'printer_power_w', labelKey: 'profilePage.calc.printerPower', step: 1, unit: 'watt' },
      { key: 'power_hotend_w', labelKey: 'profilePage.calculator.powerHotend', step: 1, unit: 'watt' },
      { key: 'power_bed_w', labelKey: 'profilePage.calculator.powerBed', step: 1, unit: 'watt' },
      { key: 'power_steppers_w', labelKey: 'profilePage.calculator.powerSteppers', step: 1, unit: 'watt' },
      { key: 'power_electronics_w', labelKey: 'profilePage.calculator.powerElectronics', step: 1, unit: 'watt' },
    ],
  },
];

const unitLabel = (
  unit: FieldUnit,
  currency: string,
  t: (key: string) => string,
): string => {
  const symbol = currencySymbol(currency);
  switch (unit) {
    case 'money':
      return symbol;
    case 'moneyPerHour':
      return `${symbol}/${t('profilePage.calculator.hourAbbr')}`;
    case 'moneyPerKwh':
      return `${symbol}/${t('profilePage.calculator.kwhAbbr')}`;
    case 'percent':
      return '%';
    case 'watt':
      return t('profilePage.calculator.wattAbbr');
    case 'hour':
      return t('profilePage.calculator.hourAbbr');
  }
};

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
            <section>
              <h3 className="mb-3 text-sm font-semibold text-cyan-100">
                {t('adminCalculatorDefaults.currencyTitle')}
              </h3>
              <label className="block max-w-xs">
                <span className="mb-1.5 block text-xs font-medium text-slate-400">
                  {t('adminCalculatorDefaults.currencyLabel')}
                </span>
                <select
                  value={profileDefaults.currency}
                  onChange={(event) => setProfileDefaults((current) => current
                    ? { ...current, currency: event.target.value }
                    : current)}
                  className="w-full rounded-lg border border-white/10 bg-slate-950/45 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  {DEFAULTS_CURRENCIES.map((code) => (
                    <option key={code} value={code}>{code}</option>
                  ))}
                </select>
              </label>
              <p className="mt-2 max-w-2xl text-xs leading-5 text-slate-400">
                {t('adminCalculatorDefaults.currencyHint')}
              </p>
            </section>
            {/* One group per column: the fields that add up to the same thing read down
                together instead of wrapping across unrelated neighbours. */}
            <div className="grid items-start gap-6 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
            {DEFAULT_FIELD_GROUPS.map((group) => (
              <section key={group.titleKey} className="min-w-0">
                <h3 className="mb-3 text-sm font-semibold text-cyan-100">{t(group.titleKey)}</h3>
                <div className="flex flex-col gap-3">
                  {group.fields.map((field) => (
                    <label key={field.key} className="block">
                      <span className="mb-1.5 block text-xs font-medium text-slate-400">{t(field.labelKey)}</span>
                      <span className="inline-flex w-max items-center gap-1.5 rounded-lg border border-white/10 bg-slate-950/45 pr-2.5 focus-within:ring-2 focus-within:ring-purple-500">
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
                          className="w-16 rounded-lg bg-transparent px-2.5 py-1.5 text-right text-white focus:outline-none"
                        />
                        <span className="shrink-0 whitespace-nowrap text-xs text-slate-500">
                          {unitLabel(field.unit, profileDefaults.currency, t)}
                        </span>
                      </span>
                    </label>
                  ))}
                  {/* The step and the direction are one decision, so they stand together
                      here exactly as they do in the person's own economics. */}
                  {group.titleKey === 'adminCalculatorDefaults.finalPrice' ? (
                    <label className="block">
                      <span className="mb-1.5 block text-xs font-medium text-slate-400">
                        {t('profilePage.calc.roundingMode')}
                      </span>
                      <select
                        value={profileDefaults.rounding_mode}
                        onChange={(event) => setProfileDefaults((current) => current
                          ? { ...current, rounding_mode: event.target.value as CalculatorProfileDefaults['rounding_mode'] }
                          : current)}
                        className="w-max rounded-lg border border-white/10 bg-slate-950/45 px-2.5 py-1.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                      >
                        <option value="up">{t('profilePage.calc.roundingModeUp')}</option>
                        <option value="nearest">{t('profilePage.calc.roundingModeNearest')}</option>
                        <option value="down">{t('profilePage.calc.roundingModeDown')}</option>
                      </select>
                    </label>
                  ) : null}
                </div>
              </section>
            ))}
            </div>

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
