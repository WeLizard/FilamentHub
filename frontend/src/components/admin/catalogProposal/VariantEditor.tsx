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
  FilamentPropertyClaim,
} from '../../../types/api';
import {
  HIDDEN_FIELDS, MARKET_CHILD, cellText, filamentVisual, listValues, marketIndicesFor, rowKey,
  type CellEdit, type ProposalRow,
} from '../../../utils/catalogProposalEdit';
import { countryName, sortedCountries } from '../../../utils/countries';
import { FilamentFeaturesEditor } from '../../FilamentFeaturesEditor';
import {
  FEATURE_FIELDS, PROPOSAL_FIELDS, SHEET_GROUPS, TECHNICAL_KEYS, fieldSpec, type FieldGroup,
} from './fieldSpecs';
import { ProposalFieldControl } from './ProposalFieldControl';
import { ProvenanceButton, type FieldEvidence } from './ProvenanceButton';
import { SourceFactsPanels } from './SourceFactsPanels';

// Controls take the width their content needs (DESIGN_SYSTEM: content-appropriate control sizing),
// so several fit on one row instead of every input spanning the whole panel.
const widthFor = (kind: string, span: number): string => {
  if (kind === 'bool') return 'w-auto';
  if (kind === 'number') return 'w-28';
  if (kind === 'colorHex') return 'w-44';
  if (kind === 'country') return 'w-40';
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
  onEdit: (sheet: CatalogImportSheet, edits: CellEdit[]) => void;
  onAddRow: (sheet: CatalogImportSheet, row: ProposalRow) => void;
  onRemoveRow: (sheet: CatalogImportSheet, index: number) => void;
  onClose: () => void;
  /** The only record of its sheet: shown directly, nothing to go back to. */
  standalone?: boolean;
}

export function VariantEditor({
  sheet, row, index, rowNumber, draft, disabled, readonly, coverageLine, evidence, facts, marketErrors = [], onEdit, onAddRow, onRemoveRow, onClose, standalone = false,
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
    ...(sheet === 'filaments' ? ['density', ...FEATURE_FIELDS] : []),
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
          <label className="inline-flex min-w-0 items-center gap-2 text-sm text-gray-200">{control}<span className="truncate">{name}</span></label>
          {provenance(targetSheet, targetRow, field)}
        </div>
        : <>
          <div className="mb-1 flex items-center gap-1 text-xs text-gray-400">
            <span className="truncate">{name}</span>
            {provenance(targetSheet, targetRow, field)}
          </div>
          {control}
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

  const grid = (fields: string[], targetSheet = sheet, targetRow = row, targetIndex = index) => {
    const present = fields.filter((field) => field in targetRow);
    return present.length === 0 ? null
      : <div className="flex flex-wrap items-start gap-x-4 gap-y-2.5">{present.map((field) => renderField(targetSheet, targetRow, targetIndex, field))}</div>;
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
        {columns.map((column) => <span key={column} className="truncate">{label(column)}</span>)}
        {isBrand && <span className="truncate">{label('shop_links')}</span>}
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
          <p className="min-w-0 flex-1 truncate text-xs text-gray-400 max-lg:basis-full max-lg:order-last" title={key}>
            {t(`adminCatalogImport.sheets.${sheetLabelKey(sheet)}`)} · #{rowNumber} · <span className="font-mono text-gray-500">{key}</span>
          </p>
          {!standalone && <button type="button" onClick={onClose} aria-label={t('adminCatalogImport.curation.closeEditor')}
            className="hidden rounded-lg p-1 text-gray-400 transition hover:bg-white/10 hover:text-white lg:inline-flex">
            <X className="h-4 w-4" />
          </button>}
        </div>
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          {logoUrl && logoUrl !== failedLogo && <div className="flex h-9 w-24 shrink-0 items-center justify-center rounded-lg border border-white/10 p-1.5"
            style={{ backgroundColor: cellText(row.logo_bg) || 'transparent' }}>
            <img src={logoUrl} alt={cellText(row.name)} referrerPolicy="no-referrer"
              className="max-h-full max-w-full object-contain" onError={() => setFailedLogo(logoUrl)} />
          </div>}
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
