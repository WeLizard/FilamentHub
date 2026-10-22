import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { CatalogImportDraft, CatalogImportSheet } from '../../../types/api';
import {
  fieldSpread, isTruthyCell, type MarketGroup, type ProposalRow,
} from '../../../utils/catalogProposalEdit';
import { countryName } from '../../../utils/countries';
import { BULK_FIELDS, MARKET_DEFAULT_FIELDS, fieldSpec, type BulkFieldDef } from './fieldSpecs';
import { ProposalFieldControl } from './ProposalFieldControl';

const targetSheet = (sheet: CatalogImportSheet, def: BulkFieldDef): CatalogImportSheet =>
  def.market ? (sheet === 'brands' ? 'brand_markets' : 'filament_markets') : sheet;

const initialValue = (sheet: CatalogImportSheet, def: BulkFieldDef): unknown => {
  const spec = fieldSpec(targetSheet(sheet, def), def.field);
  if (spec.kind === 'bool') return true;
  if (spec.kind === 'availability' || spec.kind === 'marketAvailability' || spec.kind === 'select') return spec.options?.[0] ?? '';
  return '';
};

interface BulkEditBarProps {
  sheet: CatalogImportSheet;
  count: number;
  total: number;
  disabled: boolean;
  onSelectAll: () => void;
  onClear: () => void;
  /** Countries present in the market rows of the whole sheet; empty when there are none. */
  countries: Array<{ code: string; name: string }>;
  /** One country picked in the switcher: market edits go to it alone. */
  fixedCountry: string | null;
  onApply: (def: BulkFieldDef, value: unknown, countries: string[] | null) => void;
  /** How many rows an apply would change, so a pick that reaches nothing cannot be applied. */
  targetCount: (def: BulkFieldDef, countries: string[] | null) => number;
}

/** Sets one field once for every selected row. */
export function BulkEditBar({ sheet, count, total, disabled, countries, fixedCountry, onSelectAll, onClear, onApply, targetCount }: BulkEditBarProps) {
  const { t } = useTranslation();
  const fields = BULK_FIELDS[sheet];
  const [fieldId, setFieldId] = useState(fields[0].id);
  const def = fields.find((item) => item.id === fieldId) ?? fields[0];
  const [value, setValue] = useState<unknown>(() => initialValue(sheet, fields[0]));
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [open, setOpen] = useState(false);
  const name = (item: BulkFieldDef) => item.field === 'enabled'
    ? t('adminCatalogImport.curation.includeRecord')
    : t(`adminCatalogImport.curation.fieldNames.${item.field}`, { defaultValue: item.field.replaceAll('_', ' ') });
  const label = (item: BulkFieldDef) => item.market ? `${t('adminCatalogImport.curation.groups.markets')}: ${name(item)}` : name(item);

  useEffect(() => {
    setFieldId(fields[0].id);
    setValue(initialValue(sheet, fields[0]));
  }, [sheet, fields]);

  const ready = value !== '' && value !== null && value !== undefined;
  const pickedCountries = def.market
    ? (fixedCountry ? [fixedCountry] : countries.map((c) => c.code).filter((code) => !skipped.has(code))) : null;
  const reachesRows = targetCount(def, pickedCountries) > 0;
  if (!open) {
    return (
      <div role="group" aria-label={t('adminCatalogImport.curation.bulkEdit')}
        className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-indigo-400/30 bg-indigo-500/10 px-3 py-1.5 text-sm">
        <span className="font-semibold text-indigo-100">{t('adminCatalogImport.curation.selectedCount', { count })}</span>
        <button type="button" disabled={disabled} onClick={() => setOpen(true)} className="text-indigo-200 underline underline-offset-2 disabled:opacity-40">
          {t('adminCatalogImport.curation.changeField')}
        </button>
        {count < total && <button type="button" onClick={onSelectAll} className="text-xs text-indigo-200 underline underline-offset-2">
          {t('adminCatalogImport.curation.selectAll', { count: total })}
        </button>}
        <button type="button" onClick={onClear} className="ml-auto text-xs text-gray-300 underline underline-offset-2">
          {t('adminCatalogImport.curation.clearSelection')}
        </button>
      </div>
    );
  }
  return (
    <div role="group" aria-label={t('adminCatalogImport.curation.bulkEdit')}
      className="flex flex-wrap items-end gap-x-3 gap-y-2 rounded-xl border border-indigo-400/30 bg-indigo-500/10 px-3 py-2.5">
      <p className="self-center text-sm font-semibold text-indigo-100">
        {t('adminCatalogImport.curation.selectedCount', { count })}
      </p>
      <label className="text-xs text-gray-300">
        {t('adminCatalogImport.curation.bulkField')}
        <select value={def.id} disabled={disabled}
          onChange={(event) => {
            const next = fields.find((item) => item.id === event.target.value) ?? fields[0];
            setFieldId(next.id);
            setValue(initialValue(sheet, next));
          }}
          className="mt-1 block h-9 max-w-60 rounded-lg border border-white/15 bg-slate-900 px-2.5 text-sm text-white">
          {fields.map((item) => <option key={item.id} value={item.id}>{label(item)}</option>)}
        </select>
      </label>
      <div className="min-w-32 max-w-56 flex-1 basis-40 text-xs text-gray-300">
        <span className="mb-1 block">{t('adminCatalogImport.curation.bulkValue')}</span>
        <div className="flex h-9 items-center">
          <ProposalFieldControl key={def.id} sheet={targetSheet(sheet, def)} field={def.field} value={value} disabled={disabled}
            label={`${label(def)} · ${t('adminCatalogImport.curation.bulkValue')}`} onChange={setValue} />
        </div>
      </div>
      {def.market && !fixedCountry && countries.length > 1 && <fieldset className="basis-full text-xs text-gray-300">
        <legend className="mb-1">{t('adminCatalogImport.curation.bulkCountries')}</legend>
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {countries.map((country) => <label key={country.code} className="inline-flex items-center gap-1.5">
            <input type="checkbox" checked={!skipped.has(country.code)} disabled={disabled}
              onChange={(event) => setSkipped((current) => {
                const next = new Set(current);
                if (event.target.checked) next.delete(country.code);
                else next.add(country.code);
                return next;
              })} className="h-4 w-4 accent-purple-500" />
            {country.name}
          </label>)}
        </div>
      </fieldset>}
      <button type="button" disabled={disabled || !ready || !reachesRows}
        onClick={() => onApply(def, value, pickedCountries)}
        className="h-9 rounded-lg bg-indigo-500 px-3 text-sm font-semibold text-white transition hover:bg-indigo-400 disabled:opacity-40">
        {t('adminCatalogImport.curation.bulkApply', { count })}
      </button>
      <div className="ml-auto flex items-center gap-3 self-center text-xs">
        {count < total && <button type="button" onClick={onSelectAll} className="text-indigo-200 underline underline-offset-2">
          {t('adminCatalogImport.curation.selectAll', { count: total })}
        </button>}
        <button type="button" onClick={onClear} className="text-gray-300 underline underline-offset-2">
          {t('adminCatalogImport.curation.clearSelection')}
        </button>
      </div>
    </div>
  );
}

interface MarketDefaultsPanelProps {
  groups: MarketGroup[];
  draft: CatalogImportDraft;
  disabled: boolean;
  onlyDiffering: boolean;
  differingCount: number;
  onToggleDiffering: () => void;
  onApply: (indices: number[], field: string, value: unknown) => void;
}

function TriStateCheckbox({ checked, mixed, disabled, label, onChange }: {
  checked: boolean; mixed: boolean; disabled: boolean; label: string; onChange: (checked: boolean) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = mixed;
  }, [mixed]);
  return <input ref={ref} type="checkbox" aria-label={label} checked={checked} disabled={disabled}
    onChange={(event) => onChange(event.target.checked)} className="h-4 w-4 accent-purple-500" />;
}

/** One compact row per country: its values are written into every market row of that country. */
export function MarketDefaultsPanel({ groups, draft, disabled, onlyDiffering, differingCount, onToggleDiffering, onApply }: MarketDefaultsPanelProps) {
  const { t, i18n } = useTranslation();
  const rows: ProposalRow[] = draft.filament_markets;
  const label = (name: string) => name === 'enabled'
    ? t('adminCatalogImport.curation.includeRecord')
    : t(`adminCatalogImport.curation.fieldNames.${name}`, { defaultValue: name.replaceAll('_', ' ') });
  const brands = new Set(groups.map((group) => group.brandKey));

  return (
    <section className="space-y-1.5 rounded-xl bg-white/[0.04] px-3 py-2" aria-label={t('adminCatalogImport.curation.marketDefaults')}>
      {(groups.length > 1 || differingCount > 0 || onlyDiffering) && <div className="flex flex-wrap items-center justify-between gap-2">
        {groups.length > 1 && <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-400">{t('adminCatalogImport.curation.marketDefaults')}</h4>}
        {(differingCount > 0 || onlyDiffering) && <label className="inline-flex items-center gap-2 text-xs text-gray-200">
          <input type="checkbox" checked={onlyDiffering} onChange={onToggleDiffering} className="h-4 w-4 accent-purple-500" />
          {t('adminCatalogImport.curation.onlyDiffering', { count: differingCount })}
        </label>}
      </div>}
      {groups.map((group) => {
        const country = countryName(group.country, i18n?.language ?? 'en');
        const title = [brands.size > 1 ? group.brandKey : '', groups.length > 1 ? country : t('adminCatalogImport.curation.marketDefaultFor', { country })]
          .filter(Boolean).join(' · ');
        return <div key={group.id} className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <p className="min-w-28 text-sm font-medium text-gray-200">{title}</p>
          {MARKET_DEFAULT_FIELDS.map((field) => {
            const spread = fieldSpread(rows, group.indices, field);
            const spec = fieldSpec('filament_markets', field);
            const fieldLabel = `${label(field)} · ${title}`;
            return spec.kind === 'bool'
              ? <label key={field} className="inline-flex h-9 items-center gap-2 text-sm text-gray-200">
                <TriStateCheckbox disabled={disabled} label={fieldLabel} mixed={!spread.uniform}
                  checked={isTruthyCell(spread.value, false)}
                  onChange={(checked) => onApply(group.indices, field, checked)} />
                {label(field)}
              </label>
              : <div key={field} className="w-44">
                <ProposalFieldControl sheet="filament_markets" field={field} disabled={disabled} label={fieldLabel}
                  value={spread.uniform ? spread.value : ''} onChange={(value) => onApply(group.indices, field, value)} />
              </div>;
          })}
          <span className="text-xs text-gray-400">{t('adminCatalogImport.curation.appliesTo', { count: group.indices.length })}</span>
        </div>;
      })}
    </section>
  );
}
