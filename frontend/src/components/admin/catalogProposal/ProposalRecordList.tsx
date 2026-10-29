import { useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import type { CatalogImportPlanRow, CatalogImportSheet } from '../../../types/api';
import {
  cellText, filamentVisual, rowKey, type FactCoverage, type ProposalRow, factCoverageNeedsAttention,
} from '../../../utils/catalogProposalEdit';
import { AdminPager } from '../AdminPager';
import { MaterialClassification, type MaterialClass } from './MaterialClassification';

export interface ListRow {
  row: ProposalRow;
  index: number;
}

export interface MarketCell {
  country: string;
  text: string;
}

interface ProposalRecordListProps {
  sheet: CatalogImportSheet;
  rows: ListRow[];
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  selected: Set<number>;
  onSelect: (indices: number[], checked: boolean) => void;
  openIndex: number | null;
  onOpen: (index: number) => void;
  planByRow: Map<number, CatalogImportPlanRow>;
  coverage: (key: string) => FactCoverage | undefined;
  /** Market state of a record: one cell per country shown. */
  marketCells: (row: ProposalRow) => MarketCell[];
  differs: Set<number>;
  /** With a shared market default, rows that match it show no market chip. */
  hasDefault: boolean;
  /** Brand key joins the line header only when the draft holds several brands. */
  showBrand: boolean;
  disabled: boolean;
  /** Beside an open editor: one line per record, no market column. */
  narrow?: boolean;
  /** Server classification of a record's material type, when a current preview has one. */
  materialOf?: (row: ProposalRow) => MaterialClass | undefined;
}

const WIDE_GRID = 'grid items-center gap-x-3 grid-cols-[auto_minmax(0,1fr)_auto] sm:grid-cols-[auto_minmax(0,1fr)_11rem_1.25rem]';
const NARROW_GRID = 'grid items-center gap-x-3 grid-cols-[auto_minmax(0,1fr)_auto]';
const MAX_CHIPS = 2;

function IndeterminateCheckbox({ checked, indeterminate, onChange, label, disabled }: {
  checked: boolean; indeterminate: boolean; onChange: (checked: boolean) => void; label: string; disabled: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return <input ref={ref} type="checkbox" aria-label={label} checked={checked} disabled={disabled}
    onChange={(event) => onChange(event.target.checked)} className="h-4 w-4 accent-purple-500" />;
}

const typeOf = (sheet: CatalogImportSheet, row: ProposalRow, showBrand: boolean): string => sheet === 'filaments'
  ? [showBrand ? row.brand_key : '', row.material_type].map(cellText).filter(Boolean).join(' · ') : '';
const lineOf = (row: ProposalRow): string => cellText(row.line).trim();

/** "240–260", "240" when both ends match, "240–?" when an end is missing; null when there is nothing. */
const rangeText = (row: ProposalRow, min: string, max: string): { text: string; partial: boolean } | null => {
  const low = cellText(row[min]).trim();
  const high = cellText(row[max]).trim();
  if (!low && !high) return null;
  if (!low || !high) return { text: `${low || '?'}–${high || '?'}`, partial: true };
  return { text: low === high ? low : `${low}–${high}`, partial: false };
};

export function ProposalRecordList({
  sheet, rows, page, pageSize, onPageChange, selected, onSelect, openIndex, onOpen,
  planByRow, coverage, marketCells, differs, hasDefault, showBrand, disabled, narrow = false, materialOf,
}: ProposalRecordListProps) {
  const { t } = useTranslation();
  const GRID = narrow ? NARROW_GRID : WIDE_GRID;

  const SINGLES = '\u0001';
  /**
   * Material type first; inside it the lines with two or more records, then every one-record line
   * together as "single items". Each level knows exactly the rows it owns.
   */
  const layout = useMemo(() => {
    if (sheet !== 'filaments') return { ordered: rows, byType: new Map<string, number[]>(), byLine: new Map<string, number[]>(), lineKey: new Map<number, string>(), onlySingles: new Set<string>() };
    const perLine = new Map<string, number>();
    for (const { row } of rows) {
      const key = `${typeOf(sheet, row, showBrand)}\u0000${lineOf(row)}`;
      perLine.set(key, (perLine.get(key) ?? 0) + 1);
    }
    const types = new Map<string, ListRow[]>();
    for (const item of rows) {
      const type = typeOf(sheet, item.row, showBrand);
      types.set(type, [...(types.get(type) ?? []), item]);
    }
    const ordered: ListRow[] = [];
    const byTypeMap = new Map<string, number[]>();
    const byLineMap = new Map<string, number[]>();
    const lineKeyMap = new Map<number, string>();
    const onlySingles = new Set<string>();
    for (const [type, items] of types) {
      const isMulti = (item: ListRow) => lineOf(item.row) !== '' && (perLine.get(`${type}\u0000${lineOf(item.row)}`) ?? 0) >= 2;
      const multi = items.filter(isMulti);
      const singles = items.filter((item) => !isMulti(item));
      if (multi.length === 0) onlySingles.add(type);
      for (const item of [...multi, ...singles]) {
        ordered.push(item);
        const key = `${type}\u0000${isMulti(item) ? lineOf(item.row) : SINGLES}`;
        lineKeyMap.set(item.index, key);
        byLineMap.set(key, [...(byLineMap.get(key) ?? []), item.index]);
        byTypeMap.set(type, [...(byTypeMap.get(type) ?? []), item.index]);
      }
    }
    return { ordered, byType: byTypeMap, byLine: byLineMap, lineKey: lineKeyMap, onlySingles };
  }, [rows, sheet, showBrand, SINGLES]);
  const { byType, byLine, lineKey, onlySingles } = layout;
  const pageCount = Math.max(1, Math.ceil(layout.ordered.length / pageSize));
  // A narrower filter can leave the current page past the end; show the last page and tell the parent.
  const currentPage = Math.min(Math.max(1, page), pageCount);
  useEffect(() => {
    if (currentPage !== page) onPageChange(currentPage);
  }, [currentPage, page, onPageChange]);
  const visible = layout.ordered.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  const header = (level: 1 | 2, title: string, members: number[], material?: MaterialClass) => {
    const selectedCount = members.filter((member) => selected.has(member)).length;
    return <div className={`${GRID} ${level === 1 ? 'mt-2 bg-white/[0.07]' : 'bg-white/[0.03] pl-4'} px-2 py-1.5`}>
      <IndeterminateCheckbox disabled={disabled} checked={selectedCount === members.length}
        indeterminate={selectedCount > 0 && selectedCount < members.length}
        label={`${t('adminCatalogImport.curation.selectGroup')} ${title}`}
        onChange={(checked) => onSelect(members, checked)} />
      <p title={title} className={`min-w-0 line-clamp-2 break-words ${level === 1 ? 'text-xs font-semibold uppercase tracking-wide text-indigo-200' : 'text-xs font-medium text-gray-300'}`}>
        {title} <span className="font-normal text-gray-500">· {members.length}</span>
        {material && <span className="ml-1.5 font-normal normal-case tracking-normal"><MaterialClassification value={material} compact /></span>}
      </p>
      <span className={`text-xs text-indigo-200 ${narrow ? '' : 'sm:col-span-2'}`}>
        {selectedCount > 0 && selectedCount < members.length
          ? t('adminCatalogImport.curation.selectedOf', { selected: selectedCount, total: members.length }) : ''}
      </span>
    </div>;
  };

  return (
    <div>
      <div className="space-y-px">
        {visible.map(({ row, index }, visibleIndex) => {
          const type = typeOf(sheet, row, showBrand);
          const previous = visible[visibleIndex - 1];
          const newType = Boolean(type) && (!previous || typeOf(sheet, previous.row, showBrand) !== type);
          const rowLineKey = lineKey.get(index) ?? '';
          const single = rowLineKey.endsWith(SINGLES);
          const soleLine = (byLine.get(rowLineKey)?.length ?? 0) === (byType.get(type)?.length ?? -1);
          const newLine = Boolean(type) && !soleLine && !(single && onlySingles.has(type))
            && (newType || lineKey.get(previous.index) !== rowLineKey);
          const typeTitle = soleLine && !single ? `${type} · ${lineOf(row)}` : type;
          const lineTitle = single ? t('adminCatalogImport.curation.singleItems') : lineOf(row);
          const rowNumber = Number(row._row ?? index + 2);
          const result = planByRow.get(rowNumber);
          const visual = sheet === 'filaments' ? filamentVisual(row) : null;
          const attention = sheet === 'filaments' && factCoverageNeedsAttention(coverage(rowKey(sheet, row)));
          const isOpen = openIndex === index;
          const name = cellText(row.name) || rowKey(sheet, row);
          // Inside a material group every name repeats; the colour is what tells the records apart.
          const colorName = sheet === 'filaments' ? cellText(row.color_name).trim() : '';
          const title = colorName || name;
          const temps = sheet === 'filaments'
            ? [rangeText(row, 'recommended_nozzle_temp_min', 'recommended_nozzle_temp_max'),
              rangeText(row, 'recommended_bed_temp_min', 'recommended_bed_temp_max')]
            : [];
          const cells = marketCells(row);
          const marker = result?.status === 'error'
            ? { tone: 'bg-red-400', text: result.message ?? t('adminCatalogImport.status.error') }
            : attention ? { tone: 'bg-amber-400', text: t('adminCatalogImport.curation.issueCoverage') }
              : differs.has(index) ? { tone: 'bg-indigo-300', text: t('adminCatalogImport.curation.differsFromDefault') } : null;
          const detail = [colorName && name !== lineOf(row) && name !== cellText(row.material_type) ? name : '',
            single ? lineOf(row) : '', visual?.finish && t(`adminCatalogImport.curation.visualTerms.${visual.finish}`, { defaultValue: visual.finish }),
            ...(visual?.effects ?? []).map((value) => t(`filamentFeatures.effects.${value}`, {
              defaultValue: t(`adminCatalogImport.curation.visualTerms.${value}`, { defaultValue: value }) }))]
            .filter(Boolean).join(' · ');
          return <div key={`${sheet}-${index}`}>
            {newType && header(1, typeTitle, byType.get(type) ?? [], materialOf?.(row))}
            {newLine && header(2, lineTitle, byLine.get(rowLineKey) ?? [])}
            <div className={`${GRID} rounded-lg px-2 py-1 transition ${isOpen ? 'bg-indigo-500/20' : 'hover:bg-white/5'}`}>
              <input type="checkbox" aria-label={`${t('adminCatalogImport.curation.selectRecord')} ${name}`} disabled={disabled}
                checked={selected.has(index)} onChange={(event) => onSelect([index], event.target.checked)}
                className="h-4 w-4 accent-purple-500" />
              <button type="button" onClick={() => onOpen(index)} aria-current={isOpen ? 'true' : undefined}
                className={`col-span-2 grid min-w-0 grid-cols-subgrid items-center gap-x-3 py-0.5 text-left ${narrow ? '' : 'sm:col-span-3'}`}>
                <span className="flex min-w-0 items-center gap-2">
                  {visual && visual.colors.length > 0 && <span className="flex shrink-0 -space-x-1" role="img"
                    aria-label={t('adminCatalogImport.curation.colorsCount', { count: visual.colors.length })}>
                    {visual.colors.slice(0, 3).map((color, colorIndex) => <span key={colorIndex} className="h-4 w-4 rounded-full border border-white/50" style={{ backgroundColor: color }} />)}
                  </span>}
                  <span className="min-w-0">
                    <span title={title} className={`block line-clamp-2 break-words text-sm leading-tight ${row.enabled === false ? 'text-gray-500 line-through' : 'text-white'}`}>{title}</span>
                    {(detail || temps.some(Boolean)) && <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 text-xs text-gray-400">
                      {detail && <span title={detail} className="min-w-0 line-clamp-2 break-words">{detail}</span>}
                      {temps.some(Boolean) && <span className="ml-auto shrink-0 whitespace-nowrap tabular-nums"
                        title={t('adminCatalogImport.curation.tempsSummary')}>
                        {temps.map((temp, tempIndex) => <span key={tempIndex}>
                          {tempIndex > 0 && <span className="text-gray-600"> / </span>}
                          <span className={temp?.partial ? 'text-amber-300' : 'text-gray-300'}>{temp ? `${temp.text}°` : '—'}</span>
                        </span>)}
                      </span>}
                    </span>}
                  </span>
                </span>
                {!narrow && <span className="hidden min-w-0 flex-wrap items-center gap-1 sm:flex">
                  {(differs.has(index) || !hasDefault) && cells.slice(0, MAX_CHIPS).map((cell) => <span key={cell.country} className="max-w-full truncate rounded bg-white/10 px-1.5 py-0.5 text-[11px] text-gray-200">
                    {cell.country}{cell.text ? ` · ${cell.text}` : ''}
                  </span>)}
                  {(differs.has(index) || !hasDefault) && cells.length > MAX_CHIPS && <span className="text-[11px] text-gray-400">+{cells.length - MAX_CHIPS}</span>}
                </span>}
                <span className="flex justify-end" title={marker?.text}>
                  {marker && <span role="img" aria-label={marker.text} className={`h-2 w-2 rounded-full ${marker.tone}`} />}
                </span>
              </button>
            </div>
          </div>;
        })}
        {layout.ordered.length === 0 && <p className="px-2 py-4 text-sm text-gray-400">{t('adminCatalogImport.curation.noRecordsFound')}</p>}
      </div>
      <div className="mt-2 flex justify-end border-t border-white/10 pt-2">
        <AdminPager page={currentPage} totalPages={pageCount} onPageChange={onPageChange} disabled={disabled}
          label={t('adminCatalogImport.curation.records')}
          previousLabel={t('adminCatalogImport.curation.previous')} nextLabel={t('adminCatalogImport.curation.next')} />
      </div>
    </div>
  );
}
