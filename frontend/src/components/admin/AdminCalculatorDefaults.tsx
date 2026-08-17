/** Admin: starting economics for new calculator profiles, globally and per country. */

import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Calculator, Download, Loader2, Trash2, Upload } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { adminAPI } from '../../api/client';
import { Dropdown } from '../Dropdown';
import type {
  CalculatorCountryDefaults,
  CalculatorCountryDefaultsMap,
  CalculatorProfileDefaults,
} from '../../types/api';
import { countryName, sortedCountries } from '../../utils/countries';
import { currencyCodes, currencySymbol, defaultCurrencyForCountry } from '../../utils/currency';
import { translateApiError } from '../../utils/translateApiError';

type NumericDefaultKey = Exclude<keyof CalculatorProfileDefaults, 'rounding_mode' | 'currency'>;
type CountryOverrideKey = Exclude<keyof CalculatorCountryDefaults, 'currency'>;

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

/** Fields a country may override. Machine wattage is hardware, not geography. */
const COUNTRY_OVERRIDABLE = new Set<string>([
  'electricity_cost_per_kwh',
  'modeling_rate_per_hour',
  'postprocessing_rate_per_hour',
  'printing_rate_per_hour',
  'amortization_rate_per_hour',
  'maintenance_cost_per_hour',
  'bed_prep_cost_per_print',
  'fixed_costs',
  'min_order_price',
  'overhead_percent',
  'markup_percent',
  'tax_rate_percent',
  'round_to_nearest',
]);

const CSV_COLUMNS = ['country', 'currency', ...Array.from(COUNTRY_OVERRIDABLE)];

// Excel outside the English locale splits on a semicolon and puts a comma-separated
// file into one cell. Writing semicolons keeps the file openable by double click.
const CSV_DELIMITER = ';';

const unitLabel = (unit: FieldUnit, currency: string, t: (key: string) => string): string => {
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

/** Units for the template legend: the currency is per row, so it stays a placeholder. */
const csvUnitLabel = (unit: FieldUnit, t: (key: string) => string): string => {
  const money = t('adminCalculatorDefaults.csvUnitCurrency');
  switch (unit) {
    case 'money':
      return money;
    case 'moneyPerHour':
      return `${money}/${t('profilePage.calculator.hourAbbr')}`;
    case 'moneyPerKwh':
      return `${money}/${t('profilePage.calculator.kwhAbbr')}`;
    case 'percent':
      return '%';
    case 'watt':
      return t('profilePage.calculator.wattAbbr');
    case 'hour':
      return t('profilePage.calculator.hourAbbr');
  }
};

const toCsv = (map: CalculatorCountryDefaultsMap): string => {
  const rows = Object.entries(map.countries).map(([code, values]) =>
    CSV_COLUMNS.map((column) => {
      if (column === 'country') return code;
      const value = values[column as keyof CalculatorCountryDefaults];
      return value == null ? '' : String(value);
    }).join(CSV_DELIMITER),
  );
  return [CSV_COLUMNS.join(CSV_DELIMITER), ...rows].join('\n');
};

/** Blank cells stay blank: an empty column means "no local value", not zero. */
const fromCsv = (text: string): CalculatorCountryDefaultsMap => {
  const lines = text
    .split(/\r?\n/)
    // The template carries a human-readable legend; it is there to be read, not imported.
    .filter((line) => line.trim().length > 0 && !line.trimStart().startsWith('#'));
  if (lines.length === 0) return { countries: {} };
  const delimiter = lines[0].includes(';') ? ';' : ',';
  const header = lines[0].split(delimiter).map((cell) => cell.trim());
  const countries: Record<string, CalculatorCountryDefaults> = {};

  lines.slice(1).forEach((line) => {
    const cells = line.split(delimiter).map((cell) => cell.trim());
    const record: Record<string, string> = {};
    header.forEach((column, index) => {
      record[column] = cells[index] ?? '';
    });
    const code = (record.country ?? '').toUpperCase();
    if (!code) return;

    const entry: CalculatorCountryDefaults = {};
    if (record.currency) entry.currency = record.currency.toUpperCase();
    COUNTRY_OVERRIDABLE.forEach((key) => {
      const raw = record[key];
      if (raw === undefined || raw === '') return;
      const value = Number(raw.replace(',', '.'));
      if (Number.isFinite(value) && value >= 0) {
        entry[key as CountryOverrideKey] = value;
      }
    });
    countries[code] = entry;
  });

  return { countries };
};

export function AdminCalculatorDefaults() {
  const { t, i18n } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [profileDefaults, setProfileDefaults] = useState<CalculatorProfileDefaults | null>(null);
  const [countryDefaults, setCountryDefaults] = useState<CalculatorCountryDefaultsMap>({ countries: {} });
  const [scope, setScope] = useState<string>('global');
  // Controlled filter: left to itself the dropdown prefills it with the current
  // selection on focus, and a country list that opens showing one row is useless.
  const [scopeFilter, setScopeFilter] = useState('');
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  // What the server last confirmed. Importing a CSV fills the form and nothing more,
  // so without this a reload throws away the whole table without a word.
  const [savedSnapshot, setSavedSnapshot] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [settings, countries] = await Promise.all([
          adminAPI.getCalculatorSettings(),
          adminAPI.getCalculatorCountryDefaults(),
        ]);
        setProfileDefaults(settings.profile_defaults);
        setCountryDefaults(countries);
        setSavedSnapshot(JSON.stringify([settings.profile_defaults, countries]));
      } catch (loadError) {
        setError(translateApiError(t, loadError, t('adminCalculatorDefaults.loadError')));
      }
    })();
  }, [t]);

  const dirty = savedSnapshot !== null
    && JSON.stringify([profileDefaults, countryDefaults]) !== savedSnapshot;

  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const codes = useMemo(
    () => Object.keys(countryDefaults.countries).sort(),
    [countryDefaults],
  );
  const isGlobal = scope === 'global';
  const countryEntry = isGlobal ? null : countryDefaults.countries[scope] ?? {};
  // A country without its own currency falls back to that country's money, never to
  // the base row's: showing German values under ₽ is how euro amounts get typed in
  // as roubles.
  const activeCurrency = (isGlobal
    ? profileDefaults?.currency
    : countryEntry?.currency || defaultCurrencyForCountry(scope)) ?? 'RUB';

  const scopeOptions = useMemo(() => {
    const configuredGroup = t('adminCalculatorDefaults.groupConfigured');
    const addGroup = t('adminCalculatorDefaults.groupAdd');
    const configured = new Set(codes);
    return [
      { value: 'global', label: t('adminCalculatorDefaults.scopeGlobal') },
      ...codes.map((code) => ({
        value: code,
        label: `${countryName(code, i18n.language)} · ${code}`,
        group: configuredGroup,
      })),
      ...sortedCountries(i18n.language)
        .filter((country) => !configured.has(country.code))
        .map((country) => ({ value: country.code, label: country.name, group: addGroup })),
    ];
  }, [codes, i18n.language, t]);

  const handleScopeChange = (value: string | number) => {
    const next = String(value);
    // The dropdown clears its selection when the filter is emptied; a scope always
    // points at something.
    if (!next) return;
    if (next !== 'global' && !(next in countryDefaults.countries)) {
      setCountryDefaults((current) => ({
        countries: {
          ...current.countries,
          // The country decides the currency, so amounts are typed under the sign
          // they are actually meant in.
          [next]: { currency: defaultCurrencyForCountry(next) },
        },
      }));
    }
    setScope(next);
  };

  const save = async () => {
    if (!profileDefaults) return;
    setUpdating(true);
    setError(null);
    setSaved(false);
    try {
      const [savedDefaults, savedCountries] = await Promise.all([
        adminAPI.updateCalculatorProfileDefaults(profileDefaults),
        adminAPI.updateCalculatorCountryDefaults(countryDefaults),
      ]);
      setProfileDefaults(savedDefaults);
      setCountryDefaults(savedCountries);
      setSavedSnapshot(JSON.stringify([savedDefaults, savedCountries]));
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (saveError) {
      setError(translateApiError(t, saveError, t('adminCalculatorDefaults.saveError')));
    } finally {
      setUpdating(false);
    }
  };

  const setFieldValue = (key: NumericDefaultKey, raw: string) => {
    if (isGlobal) {
      const value = Number(raw);
      setProfileDefaults((current) => current
        ? { ...current, [key]: Number.isFinite(value) ? Math.max(0, value) : 0 }
        : current);
      return;
    }
    setCountryDefaults((current) => {
      const entry = { ...(current.countries[scope] ?? {}) };
      if (raw === '') {
        delete entry[key as CountryOverrideKey];
      } else {
        const value = Number(raw);
        entry[key as CountryOverrideKey] = Number.isFinite(value) ? Math.max(0, value) : 0;
      }
      return { countries: { ...current.countries, [scope]: entry } };
    });
  };

  const downloadTemplate = () => {
    const legend = [
      `# ${t('adminCalculatorDefaults.csvLegendIntro')}`,
      `# country — ${t('adminCalculatorDefaults.csvLegendCountry')}`,
      `# currency — ${t('adminCalculatorDefaults.csvLegendCurrency')}`,
      `# ${t('adminCalculatorDefaults.csvLegendAmounts')}`,
      `# ${t('adminCalculatorDefaults.csvLegendDecimal')}`,
      ...DEFAULT_FIELD_GROUPS.flatMap((group) => group.fields)
        .filter((field) => COUNTRY_OVERRIDABLE.has(field.key))
        // The unit is the whole question for a money column: per hour, per kWh or once.
        .map((field) => `# ${field.key} — ${t(field.labelKey)}, ${csvUnitLabel(field.unit, t)}`),
      `# ${t('adminCalculatorDefaults.csvLegendEmpty')}`,
    ].join('\n');
    const table = codes.length > 0
      ? toCsv(countryDefaults)
      : [
          CSV_COLUMNS.join(CSV_DELIMITER),
          ['RU', 'RUB', ...Array.from(COUNTRY_OVERRIDABLE).map(() => '')].join(CSV_DELIMITER),
        ].join('\n');
    const blob = new Blob([`﻿${legend}\n${table}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'calculator-country-defaults.csv';
    link.click();
    URL.revokeObjectURL(url);
  };

  const importCsv = async (file: File) => {
    try {
      setCountryDefaults(fromCsv(await file.text()));
      setScope('global');
    } catch (parseError) {
      setError(translateApiError(t, parseError, t('adminCalculatorDefaults.importFailed')));
    }
  };

  return (
    <div className="space-y-5">
      {/* The action lives on the title line: a full-width band with nothing to its right
          was empty space, and the save button sat far from what it saves. */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <Calculator className="mt-0.5 h-6 w-6 shrink-0 text-cyan-400" />
          <div className="min-w-0">
            <h2 className="text-2xl font-bold text-white">{t('adminCalculatorDefaults.title')}</h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">
              {t('adminCalculatorDefaults.description')}
            </p>
            <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-400">
              {t('adminCalculatorDefaults.existingUsers')}
            </p>
          </div>
        </div>
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
          <div className="space-y-5">
            {/* One set of values, several places it can apply. Picking the scope beats
                keeping the same fields in two cards that drift apart. */}
            <div className="flex flex-wrap items-center gap-3">
              {/* One selector rather than a chip per country: the list is as long as the
                  world, and a wall of codes is not something you can find anything in. */}
              <Dropdown
                size="sm"
                filterable
                className="w-64"
                value={scope}
                options={scopeOptions}
                onChange={handleScopeChange}
                filterValue={scopeFilter}
                onFilterChange={setScopeFilter}
                placeholder={t('adminCalculatorDefaults.scopePlaceholder')}
              />
              <span className="text-[11px] text-slate-400">
                {t('adminCalculatorDefaults.countriesConfigured', { count: codes.length })}
              </span>
              {dirty ? (
                <span className="inline-flex items-center gap-1.5 rounded-lg bg-amber-400/10 px-2.5 py-1 text-[11px] text-amber-200">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  {t('adminCalculatorDefaults.unsavedChanges')}
                </span>
              ) : null}
              <div className="ml-auto flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={downloadTemplate}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-slate-300 transition hover:bg-white/10"
                >
                  <Download className="h-3.5 w-3.5" />
                  {t('adminCalculatorDefaults.downloadTemplate')}
                </button>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-slate-300 transition hover:bg-white/10"
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

            <p className="text-[11px] leading-4 text-slate-400">
              {t('adminCalculatorDefaults.scopeHint')}
            </p>

            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-white/10 bg-slate-950/30 px-3 py-2">
              <label className="flex items-center gap-2 text-xs text-slate-400">
                {t('adminCalculatorDefaults.currencyLabel')}
                <select
                  value={activeCurrency}
                  onChange={(event) => {
                    const value = event.target.value;
                    if (isGlobal) {
                      setProfileDefaults((current) => current ? { ...current, currency: value } : current);
                      return;
                    }
                    setCountryDefaults((current) => ({
                      countries: {
                        ...current.countries,
                        [scope]: { ...(current.countries[scope] ?? {}), currency: value },
                      },
                    }));
                  }}
                  className="rounded-lg border border-white/10 bg-slate-950/45 px-2.5 py-1 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  {currencyCodes().map((code) => (
                    <option key={code} value={code}>{code}</option>
                  ))}
                </select>
              </label>
              <p className="min-w-0 flex-1 text-[11px] leading-4 text-slate-400">
                {isGlobal
                  ? t('adminCalculatorDefaults.currencyHint')
                  : t('adminCalculatorDefaults.countriesHint')}
              </p>
              {!isGlobal ? (
                <button
                  type="button"
                  onClick={() => {
                    setCountryDefaults((current) => {
                      const next = { ...current.countries };
                      delete next[scope];
                      return { countries: next };
                    });
                    setScope('global');
                  }}
                  className="inline-flex shrink-0 items-center gap-1.5 text-xs text-slate-400 transition hover:text-red-200"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  {t('adminCalculatorDefaults.removeCountry')}
                </button>
              ) : null}
            </div>

            {/* Groups hold anywhere from one field to seven. Fixed columns leave the
                short ones padded with empty space; a column flow packs them tight. */}
            <div className="columns-1 gap-4 sm:columns-2 xl:columns-3 2xl:columns-4">
              {DEFAULT_FIELD_GROUPS.map((group) => {
                const fields = isGlobal
                  ? group.fields
                  : group.fields.filter((field) => COUNTRY_OVERRIDABLE.has(field.key));
                if (fields.length === 0) return null;
                return (
                  <section
                    key={group.titleKey}
                    className="mb-4 break-inside-avoid rounded-xl border border-white/10 bg-slate-950/25 p-4"
                  >
                    <h3 className="mb-3 text-sm font-semibold text-cyan-100">{t(group.titleKey)}</h3>
                    <div className="flex flex-col gap-3">
                      {fields.map((field) => {
                        const globalValue = profileDefaults[field.key];
                        const value = isGlobal
                          ? globalValue
                          : countryEntry?.[field.key as CountryOverrideKey] ?? '';
                        return (
                          <label key={field.key} className="block">
                            <span className="mb-1 block text-xs font-medium text-slate-400">
                              {t(field.labelKey)}
                            </span>
                            <span className="flex w-full items-center justify-between gap-1.5 rounded-lg border border-white/10 bg-slate-950/45 pr-2.5 focus-within:ring-2 focus-within:ring-purple-500">
                              <input
                                type="number"
                                min={0}
                                step={field.step ?? 0.01}
                                value={value}
                                // An empty country field is not zero: it falls back to the
                                // global number, shown here as the placeholder.
                                placeholder={isGlobal ? undefined : String(globalValue)}
                                onChange={(event) => setFieldValue(field.key, event.target.value)}
                                className="w-full min-w-0 rounded-lg bg-transparent px-2.5 py-1.5 text-white focus:outline-none"
                              />
                              <span className="shrink-0 whitespace-nowrap text-xs text-slate-500">
                                {unitLabel(field.unit, activeCurrency, t)}
                              </span>
                            </span>
                          </label>
                        );
                      })}
                      {group.titleKey === 'adminCalculatorDefaults.finalPrice' && isGlobal ? (
                        <label className="block">
                          <span className="mb-1 block text-xs font-medium text-slate-400">
                            {t('profilePage.calc.roundingMode')}
                          </span>
                          <select
                            value={profileDefaults.rounding_mode}
                            onChange={(event) => setProfileDefaults((current) => current
                              ? { ...current, rounding_mode: event.target.value as CalculatorProfileDefaults['rounding_mode'] }
                              : current)}
                            className="w-full rounded-lg border border-white/10 bg-slate-950/45 px-2.5 py-1.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                          >
                            <option value="up">{t('profilePage.calc.roundingModeUp')}</option>
                            <option value="nearest">{t('profilePage.calc.roundingModeNearest')}</option>
                            <option value="down">{t('profilePage.calc.roundingModeDown')}</option>
                          </select>
                        </label>
                      ) : null}
                    </div>
                  </section>
                );
              })}
            </div>
          </div>
        ) : (
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
        )}
      </div>
    </div>
  );
}
