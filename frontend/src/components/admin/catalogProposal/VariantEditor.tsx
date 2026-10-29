import { useState, type ReactNode } from 'react';
import { ArrowLeft, ChevronDown, ChevronRight, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type {
  CatalogCurationEvidence,
  CatalogCurationSourceFact,
  CatalogCurationUnmappedFact,
  CatalogImportDraft,
  CatalogImportPlanRow,
  CatalogImportSheet,
  CatalogQuoteCheckItem,
  FilamentAdditive,
  FilamentPackaging,
  FilamentPropertyClaim,
  FilamentTechnicalProperty,
} from '../../../types/api';
import { packagingKey, packagingWeightLabel } from '../../../utils/packaging';
import {
  formatTechnicalValue, sortTechnicalProperties, technicalConditions, technicalPropertyKey,
} from '../../../utils/technicalProperties';
import {
  HIDDEN_FIELDS, MARKET_CHILD, cellText, filamentVisual, listValues, marketIndicesFor, rowKey,
  type CellEdit, type ProposalRow,
} from '../../../utils/catalogProposalEdit';
import { countryName, sortedCountries } from '../../../utils/countries';
import { FilamentFeaturesEditor } from '../../FilamentFeaturesEditor';
import {
  COMPOUND_FIELDS, FEATURE_FIELDS, ITEMIZED_FIELDS, PROPOSAL_FIELDS, SHEET_GROUPS, TECHNICAL_KEYS, fieldSpec, rangeFor, unitOf,
  type FieldGroup, type RangeFields,
} from './fieldSpecs';
import { MaterialClassification, type MaterialClass } from './MaterialClassification';
import { ProposalFieldControl } from './ProposalFieldControl';
import { ProvenanceButton, type FieldEvidence } from './ProvenanceButton';
import { SourceFactsPanels } from './SourceFactsPanels';

// Controls take the width their content needs (DESIGN_SYSTEM: content-appropriate control sizing),
// so several fit on one row instead of every input spanning the whole panel.
const FAVICON = /favicon|\.ico(?:[?#]|$)/i;

type SpecItem =
  | { kind: 'range'; range: RangeFields }
  | { kind: 'compound'; key: string; fields: string[] }
  | { kind: 'single'; field: string };

const widthFor = (kind: string, span: number): string => {
  if (kind === 'bool') return 'w-auto';
  if (kind === 'number') return 'w-36';
  if (kind === 'colorHex') return 'w-44';
  if (kind === 'country') return 'w-40';
  if (kind === 'materialType') return 'w-60';
  if (kind === 'textarea' || kind === 'colors') return 'w-full max-w-3xl';
  if (kind === 'social' || kind === 'shop') return span === 6 ? 'w-full max-w-3xl' : 'w-full xl:w-[calc(50%-0.5rem)]';
  if (kind === 'text') return span === 6 ? 'w-full max-w-xl' : 'w-72';
  return 'w-52';
};

export interface EvidenceApi {
  /** Server verdict for the quote cited by this field, when the proposal has one. */
  checkFor?: (sheet: CatalogImportSheet, key: string, field: string) => CatalogQuoteCheckItem | undefined;
  /** Records (or withdraws) the administrator's "checked by eye" for an image claim. */
  confirmImage?: (sheet: CatalogImportSheet, key: string, field: string, confirmed: boolean) => void;
  forField: (sheet: CatalogImportSheet, key: string, field: string) => FieldEvidence[];
  add: (sheet: CatalogImportSheet, key: string, field: string) => void;
  update: (index: number, changes: Partial<CatalogCurationEvidence>) => void;
  remove: (index: number) => void;
}

export interface FactsApi {
  facts: Array<{ item: CatalogCurationSourceFact; index: number }>;
  unmapped: Array<{ item: CatalogCurationUnmappedFact; index: number }>;
  onUpdateSourceFact: (index: number, changes: Partial<CatalogCurationSourceFact>) => void;
  onRemoveSourceFact: (index: number) => void;
  onAddSourceFact: () => void;
  onUpdateUnmappedFact: (index: number, changes: Partial<CatalogCurationUnmappedFact>) => void;
  onRemoveUnmappedFact: (index: number) => void;
  onAddUnmappedFact: () => void;
}

interface VariantEditorProps {
  sheet: CatalogImportSheet;
  row: ProposalRow;
  index: number;
  rowNumber: number;
  draft: CatalogImportDraft;
  disabled: boolean;
  readonly: boolean;
  coverageLine: ReactNode;
  evidence: EvidenceApi;
  facts: FactsApi | null;
  /** Preview errors of this record's market rows, shown beside the rows they concern. */
  marketErrors?: CatalogImportPlanRow[];
  /** Server classification of material_type from a preview of the current draft. */
  material?: MaterialClass;
  onEdit: (sheet: CatalogImportSheet, edits: CellEdit[]) => void;
  onAddRow: (sheet: CatalogImportSheet, row: ProposalRow) => void;
  onRemoveRow: (sheet: CatalogImportSheet, index: number) => void;
  onClose: () => void;
  /** The only record of its sheet: shown directly, nothing to go back to. */
  standalone?: boolean;
}

export function VariantEditor({
  sheet, row, index, rowNumber, draft, disabled, readonly, coverageLine, evidence, facts, marketErrors = [], material, onEdit, onAddRow, onRemoveRow, onClose, standalone = false,
}: VariantEditorProps) {
  const { t, i18n } = useTranslation();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [confirmRemove, setConfirmRemove] = useState<number | null>(null);
  const [newCountry, setNewCountry] = useState('');
  const [failedLogo, setFailedLogo] = useState('');
  const label = (field: string) => field === 'enabled'
    ? t('adminCatalogImport.curation.includeRecord')
    : t(`adminCatalogImport.curation.fieldNames.${field}`, { defaultValue: field.replaceAll('_', ' ') });
  const key = rowKey(sheet, row);
  const groups = SHEET_GROUPS[sheet];
  const known = new Set<string>([
    'enabled', 'active', 'name', ...TECHNICAL_KEYS[sheet], ...groups.flatMap((group) => group.fields),
    ...(sheet === 'filaments' ? ['density', ...FEATURE_FIELDS, ...ITEMIZED_FIELDS] : []),
  ]);
  const leftover = Object.keys(row).filter((field) => !HIDDEN_FIELDS.has(field) && !known.has(field));
  const technical = [...TECHNICAL_KEYS[sheet].filter((field) => field in row), ...leftover];
  const addable = PROPOSAL_FIELDS[sheet].filter((field) => field !== 'enabled' && !HIDDEN_FIELDS.has(field)
    && !(field in row) && !(sheet === 'filaments' && (FEATURE_FIELDS as readonly string[]).includes(field)));

  const editField = (targetSheet: CatalogImportSheet, targetIndex: number, field: string, value: unknown) =>
    onEdit(targetSheet, [{ index: targetIndex, field, value }]);

  /** The server accepts a source only for a field the row actually has (or one already cited, so it can be removed). */
  const citable = (targetSheet: CatalogImportSheet, targetRow: ProposalRow, field: string) =>
    field in targetRow || evidence.forField(targetSheet, rowKey(targetSheet, targetRow), field).length > 0;

  const provenance = (targetSheet: CatalogImportSheet, targetRow: ProposalRow, field: string) => {
    if (!citable(targetSheet, targetRow, field)) return null;
    const targetKey = rowKey(targetSheet, targetRow);
    return <ProvenanceButton label={label(field)} readonly={readonly}
      entries={evidence.forField(targetSheet, targetKey, field)}
      check={evidence.checkFor?.(targetSheet, targetKey, field)}
      onConfirmImage={evidence.confirmImage
        ? (confirmed) => evidence.confirmImage?.(targetSheet, targetKey, field, confirmed) : undefined}
      onAdd={() => evidence.add(targetSheet, targetKey, field)}
      onUpdate={evidence.update} onRemove={evidence.remove} />;
  };

  const renderField = (targetSheet: CatalogImportSheet, targetRow: ProposalRow, targetIndex: number, field: string) => {
    const spec = fieldSpec(targetSheet, field);
    const name = label(field);
    const control = <ProposalFieldControl sheet={targetSheet} field={field} value={targetRow[field]} disabled={disabled || readonly}
      label={`${name} ${rowNumber}`} onChange={(value) => editField(targetSheet, targetIndex, field, value)} />;
    return <div key={field} className={`${widthFor(spec.kind, spec.span)} min-w-0 max-w-full`}>
      {spec.kind === 'bool'
        ? <div className="flex h-9 items-center gap-1.5">
          <label className="inline-flex min-w-0 items-center gap-2 text-sm text-gray-200">{control}<span className="break-words">{name}</span></label>
          {provenance(targetSheet, targetRow, field)}
        </div>
        : <>
          <div className="mb-1 flex items-start gap-1 text-xs leading-4 text-gray-400">
            <span className="min-w-0 break-words">{name}</span>
            {provenance(targetSheet, targetRow, field)}
          </div>
          {control}
          {field === 'material_type' && targetSheet === 'filaments' && material && <p className="mt-1 text-xs">
            <MaterialClassification value={material} />
          </p>}
        </>}
    </div>;
  };

  const section = (title: string, children: ReactNode, collapsed = false, extra?: ReactNode) => {
    const heading = <span className="text-sm font-semibold text-white">{title}</span>;
    return collapsed
      ? <details className="rounded-xl border border-white/10 bg-black/10 px-3 py-2.5">
        <summary className="cursor-pointer">{heading}</summary>
        <div className="mt-3">{children}</div>
      </details>
      : <section className="rounded-xl border border-white/10 bg-black/10 px-3 py-2.5">
        <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">{heading}{extra}</div>
        {children}
      </section>;
  };

  const numberInput = (targetSheet: CatalogImportSheet, targetRow: ProposalRow, targetIndex: number, field: string, missing = false) =>
    <span className="inline-flex items-center gap-1">
      <span className={`w-20 rounded-lg ${missing ? 'ring-1 ring-amber-400/70' : ''}`}>
        <ProposalFieldControl sheet={targetSheet} field={field} value={targetRow[field]} disabled={disabled || readonly}
          label={`${label(field)} ${rowNumber}`} onChange={(value) => editField(targetSheet, targetIndex, field, value)} />
      </span>
      {provenance(targetSheet, targetRow, field)}
    </span>;

  const specRow = (key: string, name: string, content: ReactNode) =>
    <div key={key} className="flex min-w-0 flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
      <span className="break-words text-xs leading-4 text-gray-400 sm:w-32 sm:shrink-0">{name}</span>
      <span className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1">{content}</span>
    </div>;

  const renderSpec = (item: SpecItem, targetSheet: CatalogImportSheet, targetRow: ProposalRow, targetIndex: number) => {
    if (item.kind === 'single') {
      return specRow(item.field, label(item.field), numberInput(targetSheet, targetRow, targetIndex, item.field));
    }
    if (item.kind === 'compound') {
      return specRow(item.key, t(`adminCatalogImport.curation.compoundNames.${item.key}`), item.fields.map((field, position) => {
        const unit = unitOf(field);
        return <span key={field} className="inline-flex items-center gap-1.5">
          {position > 0 && <span className="text-gray-600">·</span>}
          {numberInput(targetSheet, targetRow, targetIndex, field)}
          {unit && <span className="text-xs text-gray-400">{t(`adminCatalogImport.curation.units.${unit}`)}</span>}
        </span>;
      }));
    }
    const { base, min, max } = item.range;
    const filled = (field: string) => cellText(targetRow[field]).trim() !== '';
    const missing = filled(min) === filled(max) ? null : filled(min) ? max : min;
    return specRow(base, t(`adminCatalogImport.curation.rangeNames.${base}`, { defaultValue: base.replaceAll('_', ' ') }), <>
      {numberInput(targetSheet, targetRow, targetIndex, min, missing === min)}
      <span className="text-gray-300">–</span>
      {numberInput(targetSheet, targetRow, targetIndex, max, missing === max)}
      {missing && <span className="text-xs text-amber-300">
        {t(missing === min ? 'adminCatalogImport.curation.rangeMissingMin' : 'adminCatalogImport.curation.rangeMissingMax')}
      </span>}
    </>);
  };

  /**
   * Numbers read as a "label — value" table, with both ends of a range on one line so a missing end shows;
   * everything else keeps its stacked label and its own width.
   */
  const grid = (fields: string[], targetSheet = sheet, targetRow = row, targetIndex = index) => {
    const used = new Set<string>();
    const specs: SpecItem[] = [];
    const flow: string[] = [];
    for (const field of fields) {
      if (used.has(field)) continue;
      const range = fieldSpec(targetSheet, field).kind === 'number' ? rangeFor(targetSheet, field, targetRow) : null;
      if (range && (range.min in targetRow || range.max in targetRow)) {
        used.add(range.min).add(range.max);
        specs.push({ kind: 'range', range });
        continue;
      }
      const compound = COMPOUND_FIELDS.find((item) => item.fields.includes(field));
      if (compound && compound.fields.some((name) => name in targetRow)) {
        compound.fields.forEach((name) => used.add(name));
        specs.push({ kind: 'compound', key: compound.key, fields: compound.fields });
        continue;
      }
      if (!(field in targetRow)) continue;
      used.add(field);
      if (fieldSpec(targetSheet, field).kind === 'number') specs.push({ kind: 'single', field });
      else flow.push(field);
    }
    // A lone number gains nothing from a table and stays among the other fields.
    const table = specs.some((item) => item.kind !== 'single') || specs.length > 1;
    if (!table) flow.unshift(...specs.flatMap((item) => (item.kind === 'single' ? [item.field] : [])));
    if (flow.length === 0 && !table) return null;
    return <div className="space-y-3">
      {table && <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,26rem),1fr))] gap-x-8 gap-y-1.5">
        {specs.map((item) => renderSpec(item, targetSheet, targetRow, targetIndex))}
      </div>}
      {flow.length > 0 && <div className="flex flex-wrap items-start gap-x-4 gap-y-2.5">{flow.map((field) => renderField(targetSheet, targetRow, targetIndex, field))}</div>}
    </div>;
  };

  const renderGroup = (group: FieldGroup) => {
    const title = t(`adminCatalogImport.curation.groups.${group.key}`);
    const only = group.fields.length === 1 ? group.fields[0] : null;
    // A section holding one field of the same name shows its label once, in the heading.
    if (only && only in row && label(only) === title) {
      return <div key={group.key}>{section(title, <ProposalFieldControl sheet={sheet} field={only} value={row[only]}
        disabled={disabled || readonly} label={`${title} ${rowNumber}`} onChange={(value) => editField(sheet, index, only, value)} />,
      group.collapsed, provenance(sheet, row, only))}</div>;
    }
    const content = grid(group.fields);
    return content ? <div key={group.key}>{section(title, content, group.collapsed)}</div> : null;
  };

  const colors = sheet === 'filaments' ? filamentVisual(row).colors : [];
  const child = MARKET_CHILD[sheet];
  const marketIndices = child ? marketIndicesFor(draft, sheet, key) : [];
  const additives = Array.isArray(row.additives) ? row.additives as FilamentAdditive[] : [];
  const claims = Array.isArray(row.property_claims) ? row.property_claims as FilamentPropertyClaim[] : [];
  const packagings = sheet === 'filaments' && Array.isArray(row.packagings) ? row.packagings as FilamentPackaging[] : [];
  const measurements = sheet === 'filaments' && Array.isArray(row.technical_properties)
    ? sortTechnicalProperties(row.technical_properties as FilamentTechnicalProperty[]) : [];
  const unnamedTitle = cellText(row.name) || key;
  const logoUrl = sheet === 'brands' ? cellText(row.logo_url) : '';

  const marketTable = () => {
    if (!child) return null;
    const locale = i18n?.language ?? 'en';
    const isBrand = sheet === 'brands';
    const columns = isBrand ? ['website', 'published'] : ['availability', 'published', 'market_color_name'];
    const extra = isBrand ? ['description', 'social_media_urls', 'shop_links'] : ['product_url', 'purchase_links', 'market_note', 'country'];
    const gridClass = isBrand
      ? 'justify-start grid-cols-[3.25rem_minmax(0,22rem)_6.5rem_5rem_3.5rem]'
      : 'justify-start grid-cols-[3.25rem_minmax(0,13rem)_6.5rem_minmax(0,14rem)_3.5rem]';
    const present = new Set(marketIndices.map((marketIndex) => cellText(draft[child.sheet][marketIndex].country).toUpperCase()));
    const available = sortedCountries(locale).filter((country) => !present.has(country.code));
    const first = marketIndices.length ? draft[child.sheet][marketIndices[0]] : null;
    const addCountry = () => {
      if (!newCountry) return;
      const base: ProposalRow = isBrand
        ? { enabled: true, brand_key: key, country: newCountry, published: true }
        : {
          enabled: true, filament_key: key, country: newCountry,
          availability: first?.availability ?? 'unknown', published: first?.published ?? true,
        };
      onAddRow(child.sheet, base);
      setNewCountry('');
    };
    return <div className="space-y-1.5">
      {marketIndices.length > 0 && <div className={`grid ${gridClass} items-end gap-x-2 px-1 text-[11px] text-gray-500`}>
        <span>{label('country')}</span>
        {columns.map((column) => <span key={column} className="break-words leading-tight">{label(column)}</span>)}
        {isBrand && <span className="break-words leading-tight">{label('shop_links')}</span>}
        <span />
      </div>}
      {marketIndices.map((marketIndex) => {
        const market = draft[child.sheet][marketIndex];
        const country = cellText(market.country).toUpperCase();
        const open = expanded.has(marketIndex);
        const cellLabel = (field: string) => `${label(field)} ${country}`;
        return <div key={marketIndex} className="rounded-lg bg-white/[0.04] px-1 py-1">
          <div className={`grid ${gridClass} items-center gap-x-2`}>
            <span className="truncate rounded bg-indigo-400/15 px-1.5 py-1 text-center text-xs font-semibold text-indigo-200" title={countryName(country, locale)}>{country}</span>
            {columns.map((column) => <div key={column} className="min-w-0">
              <ProposalFieldControl sheet={child.sheet} field={column} value={market[column]} disabled={disabled || readonly}
                label={cellLabel(column)} onChange={(value) => editField(child.sheet, marketIndex, column, value)} />
            </div>)}
            {isBrand && <span className="text-center text-xs text-gray-300">{listValues(Array.isArray(market.shop_links) ? market.shop_links.map((link) => cellText((link as { url?: unknown })?.url)) : market.shop_links).length}</span>}
            <span className="flex items-center justify-end gap-0.5">
              <button type="button" aria-expanded={open} aria-label={`${t('adminCatalogImport.curation.marketDetails')} ${country}`}
                onClick={() => setExpanded((current) => {
                  const next = new Set(current);
                  if (next.has(marketIndex)) next.delete(marketIndex);
                  else next.add(marketIndex);
                  return next;
                })} className="rounded p-1 text-gray-400 hover:bg-white/10 hover:text-white">
                {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </button>
              {!readonly && <button type="button" disabled={disabled} aria-label={`${t('adminCatalogImport.curation.removeMarket')} ${country}`}
                onClick={() => setConfirmRemove(marketIndex)} className="rounded p-1 text-gray-500 hover:bg-white/10 hover:text-red-300">
                <X className="h-4 w-4" />
              </button>}
            </span>
          </div>
          {marketErrors.filter((error) => error.row === Number(market._row ?? marketIndex + 2) || error.key === rowKey(child.sheet, market))
            .map((error) => <p key={`${error.row}-${error.key}`} role="alert" className="mt-1 px-1 text-xs text-red-300">
              {error.message ?? t('adminCatalogImport.status.error')}
            </p>)}
          {confirmRemove === marketIndex && <div className="mt-1.5 flex flex-wrap items-center gap-3 px-1 text-xs">
            <span className="text-amber-200">{t('adminCatalogImport.curation.removeMarketConfirm', { country: countryName(country, locale) })}</span>
            <button type="button" className="font-semibold text-red-300"
              onClick={() => { setConfirmRemove(null); onRemoveRow(child.sheet, marketIndex); }}>
              {t('adminCatalogImport.curation.removeMarket')}
            </button>
            <button type="button" className="text-gray-300" onClick={() => setConfirmRemove(null)}>{t('adminCatalogImport.serviceAccounts.cancel')}</button>
          </div>}
          {open && <div className="mt-2 flex flex-wrap items-start gap-x-4 gap-y-2.5 px-1 pb-1">
            {[...extra, 'enabled'].filter((field) => field in market || field === 'enabled').map((field) => renderField(child.sheet, market, marketIndex, field))}
          </div>}
        </div>;
      })}
      {!readonly && available.length > 0 && <div className="flex flex-wrap items-center gap-2 pt-1">
        <select aria-label={t('adminCatalogImport.curation.addMarket')} value={newCountry} disabled={disabled}
          onChange={(event) => setNewCountry(event.target.value)}
          className="h-9 min-w-0 max-w-56 rounded-lg border border-white/15 bg-slate-900 px-2.5 text-sm text-white disabled:opacity-40">
          <option value="">{t('adminCatalogImport.curation.chooseCountry')}</option>
          {available.map((country) => <option key={country.code} value={country.code}>{country.name}</option>)}
        </select>
        <button type="button" disabled={disabled || !newCountry} onClick={addCountry}
          className="h-9 rounded-lg border border-white/15 px-3 text-sm text-indigo-200 transition hover:bg-white/5 disabled:opacity-40">
          + {t('adminCatalogImport.curation.addMarket')}
        </button>
      </div>}
    </div>;
  };

  return (
    <div className="space-y-2.5">
      <div className="rounded-xl border border-white/10 bg-slate-950/50 px-3 py-3">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
          {!standalone && <button type="button" onClick={onClose}
            className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap text-sm text-indigo-200 transition hover:text-white lg:hidden">
            <ArrowLeft className="h-4 w-4" />{t('adminCatalogImport.curation.backToRecords')}
          </button>}
          <p className="min-w-0 flex-1 break-all text-xs text-gray-400 max-lg:basis-full max-lg:order-last" title={key}>
            {t(`adminCatalogImport.sheets.${sheetLabelKey(sheet)}`)} · #{rowNumber} · <span className="font-mono text-gray-500">{key}</span>
          </p>
          {!standalone && <button type="button" onClick={onClose} aria-label={t('adminCatalogImport.curation.closeEditor')}
            className="hidden rounded-lg p-1 text-gray-400 transition hover:bg-white/10 hover:text-white lg:inline-flex">
            <X className="h-4 w-4" />
          </button>}
        </div>
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          {sheet === 'brands' && (logoUrl && logoUrl !== failedLogo
            ? <div className="flex h-14 w-36 shrink-0 items-center justify-center rounded-lg border border-white/10 p-1.5"
              style={{ backgroundColor: cellText(row.logo_bg) || 'transparent' }}>
              <img src={logoUrl} alt={cellText(row.name)} referrerPolicy="no-referrer"
                className="max-h-full max-w-full object-contain" onError={() => setFailedLogo(logoUrl)} />
            </div>
            : <div className="flex h-14 w-36 shrink-0 items-center justify-center rounded-lg border border-dashed border-white/25 px-2 text-center text-xs text-gray-400">
              {t(logoUrl ? 'adminCatalogImport.curation.logoBroken' : 'adminCatalogImport.curation.noLogo')}
            </div>)}
          {'name' in row
            ? <div className="min-w-0 w-full max-w-md">
              <div className="mb-1 flex items-center gap-1 text-xs text-gray-400">
                <span>{label('name')}</span>{provenance(sheet, row, 'name')}
              </div>
              <ProposalFieldControl sheet={sheet} field="name" value={row.name} disabled={disabled || readonly}
                label={`${label('name')} ${rowNumber}`} onChange={(value) => editField(sheet, index, 'name', value)} />
            </div>
            : <h3 className="break-words text-base font-semibold text-white">{unnamedTitle}</h3>}
          <label className="inline-flex h-9 items-center gap-2 text-sm text-gray-200">
            <input type="checkbox" aria-label={`${t('adminCatalogImport.curation.includeRecord')} ${rowNumber}`}
              disabled={disabled || readonly}
              checked={row.enabled === undefined ? true : ['true', '1', 'yes', 'да'].includes(cellText(row.enabled).toLowerCase())}
              onChange={(event) => editField(sheet, index, 'enabled', event.target.checked)} className="h-4 w-4 accent-purple-500" />
            {t('adminCatalogImport.curation.includeRecord')}
          </label>
          {'active' in row && <label className="inline-flex h-9 items-center gap-2 text-sm text-gray-200">
            <ProposalFieldControl sheet={sheet} field="active" value={row.active} disabled={disabled || readonly}
              label={`${label('active')} ${rowNumber}`} onChange={(value) => editField(sheet, index, 'active', value)} />
            {label('active')}
          </label>}
          {colors.length > 0 && <span className="flex h-9 items-center gap-1" role="img"
            aria-label={t('adminCatalogImport.curation.colorsCount', { count: colors.length })}>
            {colors.map((color, colorIndex) => <span key={colorIndex} className="h-4 w-4 rounded-full border border-white/50" style={{ backgroundColor: color }} />)}
          </span>}
        </div>
        {FAVICON.test(logoUrl) && <p className="mt-2 text-xs text-amber-300">{t('adminCatalogImport.curation.logoLooksLikeFavicon')}</p>}
        {coverageLine}
      </div>

      {groups.map((group) => {
        if (sheet === 'filaments' && group.key === 'printing') {
          return <div key="composition-and-printing" className="space-y-2.5">
            {section(t('adminCatalogImport.curation.groups.properties'), <div className="space-y-3">
              {grid(['density'])}
              <fieldset disabled={disabled || readonly} className={disabled || readonly ? 'pointer-events-none opacity-60' : ''}>
                <FilamentFeaturesEditor compact allowCustom
                  effects={listValues(row.effects)} additives={additives} propertyClaims={claims}
                  onEffectsChange={(effects) => onEdit(sheet, [
                    { index, field: 'effects', value: effects },
                    ...('filler' in row ? [{ index, field: 'filler', value: effects[0] ?? 'none' }] : []),
                  ])}
                  onAdditivesChange={(value) => editField(sheet, index, 'additives', value)}
                  onPropertyClaimsChange={(value) => editField(sheet, index, 'property_claims', value)} />
              </fieldset>
            </div>, false, <span className="flex items-center gap-3">
              {FEATURE_FIELDS.filter((field) => citable(sheet, row, field)).map((field) => <span key={field} className="inline-flex items-center gap-0.5 text-xs text-gray-400">
                {label(field)}{provenance(sheet, row, field)}
              </span>)}
            </span>)}
            {renderGroup(group)}
          </div>;
        }
        if (sheet === 'filaments' && group.key === 'packaging' && packagings.length > 0) {
          return <div key={group.key}>{section(t('adminCatalogImport.curation.groups.packaging'), <div className="space-y-3">
            <ul className="flex flex-wrap gap-2">
              {packagings.map((item) => {
                const path = `packagings[${packagingKey(item)}]`;
                return <li key={path} className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-black/15 px-2.5 py-1.5 text-sm text-gray-100">
                  <span className="font-medium">{packagingWeightLabel(item, t, i18n?.language ?? 'en')}</span>
                  <span className="text-xs text-gray-400">{t(`filamentPackaging.type.${item.package_type ?? 'spool'}`)}</span>
                  <ProvenanceButton label={`${label('packagings')} ${packagingWeightLabel(item, t, i18n?.language ?? 'en')}`}
                    readonly={readonly} entries={evidence.forField(sheet, key, path)} check={evidence.checkFor?.(sheet, key, path)}
                    onConfirmImage={evidence.confirmImage ? (confirmed) => evidence.confirmImage?.(sheet, key, path, confirmed) : undefined}
                    onAdd={() => evidence.add(sheet, key, path)} onUpdate={evidence.update} onRemove={evidence.remove} />
                </li>;
              })}
            </ul>
            {grid(group.fields)}
          </div>)}</div>;
        }
        if (sheet === 'filaments' && group.key === 'technicalData' && measurements.length > 0) {
          return <div key={group.key}>{section(t('adminCatalogImport.curation.groups.technicalData'), <div className="space-y-3">
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,22rem),1fr))] gap-x-6 gap-y-1">
              {measurements.map((item) => {
                const path = `technical_properties[${technicalPropertyKey(item)}]`;
                const name = t(`technicalProperties.codes.${item.code}`, { defaultValue: item.code });
                const notes = [...technicalConditions(item, t, i18n?.language ?? 'en'), item.standard].filter(Boolean).join(' · ');
                return <li key={path} className="flex min-w-0 items-center gap-1.5 text-sm">
                  <span className="min-w-0 truncate text-gray-300" title={notes}>{name}{notes && <span className="text-xs text-gray-500"> · {notes}</span>}</span>
                  <span className="shrink-0 font-medium tabular-nums text-white">{formatTechnicalValue(item, i18n?.language ?? 'en')}</span>
                  <ProvenanceButton label={`${name} ${notes}`.trim()} readonly={readonly}
                    entries={evidence.forField(sheet, key, path)} check={evidence.checkFor?.(sheet, key, path)}
                    onConfirmImage={evidence.confirmImage ? (confirmed) => evidence.confirmImage?.(sheet, key, path, confirmed) : undefined}
                    onAdd={() => evidence.add(sheet, key, path)} onUpdate={evidence.update} onRemove={evidence.remove} />
                </li>;
              })}
            </ul>
            {grid(group.fields)}
          </div>)}</div>;
        }
        return renderGroup(group);
      })}

      {child && (marketIndices.length > 0 || !readonly) && section(t('adminCatalogImport.curation.groups.markets'), marketTable())}

      {(technical.length > 0 || addable.length > 0) && section(t('adminCatalogImport.curation.groups.other'), <div className="space-y-3">
        {grid(technical)}
        {addable.length > 0 && !readonly && <label className="flex flex-wrap items-center gap-2 text-sm text-gray-300">
          {t('adminCatalogImport.curation.addField')}
          <select aria-label={`${t('adminCatalogImport.curation.addField')} ${rowNumber}`} value="" disabled={disabled}
            onChange={(event) => { if (event.target.value) editField(sheet, index, event.target.value, ''); }}
            className="min-w-0 max-w-64 rounded-lg border border-white/15 bg-slate-900 px-2.5 py-1.5 text-sm text-white disabled:opacity-40">
            <option value="">{t('adminCatalogImport.curation.chooseField')}</option>
            {addable.map((field) => <option key={field} value={field}>{label(field)}</option>)}
          </select>
        </label>}
      </div>, true)}

      {facts && <SourceFactsPanels filamentKeys={draft.filaments.map((filament) => cellText(filament.filament_key))}
        disabled={disabled || readonly} readonly={readonly} {...facts} />}
    </div>
  );
}

function sheetLabelKey(sheet: CatalogImportSheet): string {
  return { brands: 'brands', filaments: 'filaments', brand_markets: 'brandMarkets', filament_markets: 'filamentMarkets', presets: 'presets' }[sheet];
}
