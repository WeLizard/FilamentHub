/** Admin: per-country overrides for the calculator starting economics. */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Download, Globe2, Loader2, Trash2, Upload } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { adminAPI } from '../../api/client';
import type { CalculatorCountryDefaults, CalculatorCountryDefaultsMap } from '../../types/api';
import { translateApiError } from '../../utils/translateApiError';

type CountryField = Exclude<keyof CalculatorCountryDefaults, 'currency'>;

const COUNTRY_FIELDS: Array<{ key: CountryField; labelKey: string }> = [
  { key: 'electricity_cost_per_kwh', labelKey: 'profilePage.calc.electricityCost' },
  { key: 'printing_rate_per_hour', labelKey: 'profilePage.calc.printingRate' },
  { key: 'modeling_rate_per_hour', labelKey: 'profilePage.calc.modeling' },
  { key: 'postprocessing_rate_per_hour', labelKey: 'profilePage.calc.postprocessing' },
  { key: 'amortization_rate_per_hour', labelKey: 'profilePage.calc.amortizationRate' },
  { key: 'maintenance_cost_per_hour', labelKey: 'printerCost.maintenanceLine' },
  { key: 'bed_prep_cost_per_print', labelKey: 'profilePage.calc.bedPrepCost' },
  { key: 'fixed_costs', labelKey: 'profilePage.calc.fixedCosts' },
  { key: 'min_order_price', labelKey: 'profilePage.calc.minOrderPrice' },
  { key: 'overhead_percent', labelKey: 'profilePage.calc.overheadPercent' },
  { key: 'markup_percent', labelKey: 'profilePage.calc.markupPercent' },
  { key: 'tax_rate_percent', labelKey: 'profilePage.calc.taxRatePercent' },
  { key: 'round_to_nearest', labelKey: 'profilePage.calc.roundTo' },
];

const CSV_COLUMNS = ['country', 'currency', ...COUNTRY_FIELDS.map((field) => field.key)];

const toCsv = (map: CalculatorCountryDefaultsMap): string => {
  const rows = Object.entries(map.countries).map(([code, values]) =>
    CSV_COLUMNS.map((column) => {
      if (column === 'country') return code;
      const value = values[column as keyof CalculatorCountryDefaults];
      return value == null ? '' : String(value);
    }).join(','),
  );
  return [CSV_COLUMNS.join(','), ...rows].join('\n');
};

/** Blank cells stay blank: an empty column means "no local value", not zero. */
const fromCsv = (text: string): CalculatorCountryDefaultsMap => {
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length === 0) return { countries: {} };
  const header = lines[0].split(',').map((cell) => cell.trim());
  const countries: Record<string, CalculatorCountryDefaults> = {};

  lines.slice(1).forEach((line) => {
    const cells = line.split(',').map((cell) => cell.trim());
    const record: Record<string, string> = {};
    header.forEach((column, index) => {
      record[column] = cells[index] ?? '';
    });
    const code = (record.country ?? '').toUpperCase();
    if (!code) return;

    const entry: CalculatorCountryDefaults = {};
    if (record.currency) entry.currency = record.currency.toUpperCase();
    COUNTRY_FIELDS.forEach(({ key }) => {
      const raw = record[key];
      if (raw === undefined || raw === '') return;
      const value = Number(raw.replace(',', '.'));
      if (Number.isFinite(value) && value >= 0) {
        entry[key] = value;
      }
    });
    countries[code] = entry;
  });

  return { countries };
};

export function AdminCalculatorCountryDefaults() {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [countryDefaults, setCountryDefaults] = useState<CalculatorCountryDefaultsMap | null>(null);
  const [newCountry, setNewCountry] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setCountryDefaults(await adminAPI.getCalculatorCountryDefaults());
      } catch (loadError) {
        setError(translateApiError(t, loadError, t('adminCalculatorDefaults.loadFailed')));
      }
    })();
  }, [t]);

  const codes = useMemo(
    () => Object.keys(countryDefaults?.countries ?? {}).sort(),
    [countryDefaults],
  );

  const patchCountry = (code: string, field: CountryField, raw: string) => {
    setCountryDefaults((current) => {
      if (!current) return current;
      const entry = { ...(current.countries[code] ?? {}) };
      if (raw === '') {
        delete entry[field];
      } else {
        const value = Number(raw);
        entry[field] = Number.isFinite(value) ? Math.max(0, value) : 0;
      }
      return { countries: { ...current.countries, [code]: entry } };
    });
  };

  const save = async (next?: CalculatorCountryDefaultsMap) => {
    const payload = next ?? countryDefaults;
    if (!payload) return;
    setSaving(true);
    setError(null);
    try {
      setCountryDefaults(await adminAPI.updateCalculatorCountryDefaults(payload));
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (saveError) {
      setError(translateApiError(t, saveError, t('adminCalculatorDefaults.saveFailed')));
    } finally {
      setSaving(false);
    }
  };

  const downloadTemplate = () => {
    const body = countryDefaults && codes.length > 0
      ? toCsv(countryDefaults)
      : [CSV_COLUMNS.join(','), `RU,RUB,${COUNTRY_FIELDS.map(() => '').join(',')}`].join('\n');
    const blob = new Blob([`﻿${body}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'calculator-country-defaults.csv';
    link.click();
    URL.revokeObjectURL(url);
  };

  const importCsv = async (file: File) => {
    try {
      const parsed = fromCsv(await file.text());
      setCountryDefaults(parsed);
      await save(parsed);
    } catch (parseError) {
      setError(translateApiError(t, parseError, t('adminCalculatorDefaults.importFailed')));
    }
  };

  return (
    <div className="mt-6 rounded-xl border border-white/10 bg-white/5 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-cyan-100">
          <Globe2 className="h-4 w-4" />
          {t('adminCalculatorDefaults.countriesTitle')}
        </h3>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={downloadTemplate}
            className="inline-flex items-center gap-2 rounded-lg border border-white/15 px-3 py-1.5 text-xs text-slate-200 transition hover:bg-white/10"
          >
            <Download className="h-3.5 w-3.5" />
            {t('adminCalculatorDefaults.downloadTemplate')}
          </button>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="inline-flex items-center gap-2 rounded-lg border border-white/15 px-3 py-1.5 text-xs text-slate-200 transition hover:bg-white/10"
          >
            <Upload className="h-3.5 w-3.5" />
            {t('adminCalculatorDefaults.importCsv')}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = '';
              if (file) void importCsv(file);
            }}
          />
        </div>
      </div>

      <p className="mt-2 max-w-3xl text-xs leading-5 text-slate-400">
        {t('adminCalculatorDefaults.countriesHint')}
      </p>

      {error && (
        <div className="mt-3 rounded-lg border border-red-500/30 bg-red-900/20 p-3 text-sm text-red-300">{error}</div>
      )}
      {saved && (
        <div className="mt-3 rounded-lg border border-emerald-400/25 bg-emerald-400/10 p-3 text-sm text-emerald-100">
          {t('adminCalculatorDefaults.saved')}
        </div>
      )}

      {countryDefaults ? (
        <div className="mt-4 space-y-4">
          {codes.length === 0 ? (
            <p className="text-xs text-slate-500">{t('adminCalculatorDefaults.countriesEmpty')}</p>
          ) : null}

          {codes.map((code) => (
            <section key={code} className="rounded-lg border border-white/10 bg-slate-950/30 p-3">
              <div className="mb-3 flex items-center justify-between gap-3">
                <span className="text-sm font-semibold text-white">{code}</span>
                <button
                  type="button"
                  onClick={() => setCountryDefaults((current) => {
                    if (!current) return current;
                    const next = { ...current.countries };
                    delete next[code];
                    return { countries: next };
                  })}
                  className="inline-flex items-center gap-1.5 text-xs text-slate-400 transition hover:text-red-200"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  {t('adminCalculatorDefaults.removeCountry')}
                </button>
              </div>
              <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(9rem,max-content))]">
                <label className="block">
                  <span className="mb-1 block text-[11px] text-slate-400">
                    {t('adminCalculatorDefaults.currencyLabel')}
                  </span>
                  <input
                    value={countryDefaults.countries[code]?.currency ?? ''}
                    maxLength={4}
                    placeholder="—"
                    onChange={(event) => setCountryDefaults((current) => current
                      ? {
                          countries: {
                            ...current.countries,
                            [code]: {
                              ...current.countries[code],
                              currency: event.target.value.toUpperCase() || undefined,
                            },
                          },
                        }
                      : current)}
                    className="w-16 rounded-lg border border-white/10 bg-slate-950/45 px-2.5 py-1.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </label>
                {COUNTRY_FIELDS.map((field) => (
                  <label key={field.key} className="block">
                    <span className="mb-1 block text-[11px] text-slate-400">{t(field.labelKey)}</span>
                    <input
                      type="number"
                      min={0}
                      step={0.01}
                      placeholder="—"
                      value={countryDefaults.countries[code]?.[field.key] ?? ''}
                      onChange={(event) => patchCountry(code, field.key, event.target.value)}
                      className="w-20 rounded-lg border border-white/10 bg-slate-950/45 px-2.5 py-1.5 text-right text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                  </label>
                ))}
              </div>
            </section>
          ))}

          <div className="flex flex-wrap items-center gap-3 border-t border-white/10 pt-4">
            <input
              value={newCountry}
              maxLength={2}
              placeholder={t('adminCalculatorDefaults.countryCodePlaceholder')}
              onChange={(event) => setNewCountry(event.target.value.toUpperCase())}
              className="w-20 rounded-lg border border-white/10 bg-slate-950/45 px-2.5 py-1.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <button
              type="button"
              disabled={newCountry.trim().length < 2}
              onClick={() => {
                const code = newCountry.trim().toUpperCase();
                setCountryDefaults((current) => current
                  ? { countries: { ...current.countries, [code]: current.countries[code] ?? {} } }
                  : current);
                setNewCountry('');
              }}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-xs text-slate-200 transition hover:bg-white/10 disabled:opacity-40"
            >
              {t('adminCalculatorDefaults.addCountry')}
            </button>
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving}
              className="ml-auto inline-flex items-center gap-2 rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-50"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {t('adminCalculatorDefaults.saveCountries')}
            </button>
          </div>
        </div>
      ) : (
        <Loader2 className="mt-4 h-5 w-5 animate-spin text-slate-400" />
      )}
    </div>
  );
}
