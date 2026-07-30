import { useRef, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Link2,
  Loader2,
  Unlink,
  Upload,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  spoolsAPI,
  type SpoolImportColumnMapping,
  type SpoolImportPreviewResponse,
  type SpoolImportSemanticField,
  type SpoolImportUnit,
  type SpoolManagerPreviewRow,
} from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { ModalOverlay } from './ModalOverlay';
import { toast } from './Toast';

interface SpoolImportButtonProps {
  onImported: () => void;
}

const rowWarningKey = (warning: string): string =>
  `profilePage.spoolManagerImport.warnings.${warning}`;

export const SpoolImportButton: React.FC<SpoolImportButtonProps> = ({
  onImported,
}) => {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<SpoolImportPreviewResponse | null>(null);
  const [mapping, setMapping] = useState<SpoolImportColumnMapping | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [isOpen, setIsOpen] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resetAndClose = () => {
    setIsOpen(false);
    setFile(null);
    setPreview(null);
    setMapping(null);
    setSelected(new Set());
    setError(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  const close = () => {
    if (isImporting) return;
    resetAndClose();
  };

  const previewFile = async (nextFile: File) => {
    setFile(nextFile);
    setPreview(null);
    setSelected(new Set());
    setError(null);
    setIsOpen(true);
    setIsPreviewing(true);
    try {
      const result = await spoolsAPI.previewImport(nextFile);
      setPreview(result);
      setMapping(result.suggested_mapping);
      setSelected(
        new Set(
          result.rows
            .filter((row) => row.status === 'ready')
            .map((row) => row.fingerprint),
        ),
      );
    } catch (requestError: any) {
      setError(
        translateApiError(
          t,
          requestError?.response?.data?.detail,
          t('profilePage.spoolManagerImport.previewError'),
        ),
      );
    } finally {
      setIsPreviewing(false);
    }
  };

  const applyMapping = async () => {
    if (!file || !mapping) return;
    setError(null);
    setIsPreviewing(true);
    try {
      const result = await spoolsAPI.previewImport(file, mapping);
      setPreview(result);
      setMapping(result.suggested_mapping ?? mapping);
      setSelected(
        new Set(
          result.rows
            .filter((row) => row.status === 'ready')
            .map((row) => row.fingerprint),
        ),
      );
    } catch (requestError: any) {
      setError(
        translateApiError(
          t,
          requestError?.response?.data?.detail,
          t('profilePage.spoolManagerImport.mappingError'),
        ),
      );
    } finally {
      setIsPreviewing(false);
    }
  };

  const toggleRow = (row: SpoolManagerPreviewRow) => {
    if (row.status !== 'ready') return;
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(row.fingerprint)) next.delete(row.fingerprint);
      else next.add(row.fingerprint);
      return next;
    });
  };

  const toggleAll = () => {
    if (!preview) return;
    const ready = preview.rows.filter((row) => row.status === 'ready');
    const allSelected = ready.length > 0 && ready.every((row) => selected.has(row.fingerprint));
    setSelected(
      allSelected ? new Set() : new Set(ready.map((row) => row.fingerprint)),
    );
  };

  const runImport = async () => {
    if (!file || selected.size === 0) return;
    setError(null);
    setIsImporting(true);
    try {
      const result = await spoolsAPI.importFile(
        file,
        Array.from(selected),
        preview?.detected_format === 'custom_csv' ? mapping ?? undefined : undefined,
      );
      toast.success(
        t('profilePage.spoolManagerImport.success', { count: result.created }),
        undefined,
        'spool-import',
      );
      onImported();
      resetAndClose();
    } catch (requestError: any) {
      setError(
        translateApiError(
          t,
          requestError?.response?.data?.detail,
          t('profilePage.spoolManagerImport.importError'),
        ),
      );
    } finally {
      setIsImporting(false);
    }
  };

  const readyRows = preview?.rows.filter((row) => row.status === 'ready') ?? [];
  const allReadySelected =
    readyRows.length > 0 && readyRows.every((row) => selected.has(row.fingerprint));
  const canApplyMapping = Boolean(
    mapping?.fields.initial_weight || mapping?.fields.remaining_weight,
  );

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={(event) => {
          const nextFile = event.target.files?.[0];
          if (nextFile) void previewFile(nextFile);
        }}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-gray-200 transition hover:border-purple-400/50 hover:bg-purple-500/10 hover:text-white"
      >
        <Upload className="h-4 w-4" />
        <span>{t('profilePage.spoolManagerImport.button')}</span>
      </button>

      {isOpen && (
        <ModalOverlay
          onClose={close}
          closeOnOverlayClick={!isImporting}
          closeOnEscape={!isImporting}
        >
          <div className="w-full max-w-4xl overflow-hidden rounded-2xl border border-white/15 bg-slate-950 shadow-2xl">
            <div className="flex items-start justify-between gap-4 border-b border-white/10 px-5 py-4 md:px-6">
              <div>
                <div className="flex items-center gap-2">
                  <div className="rounded-lg bg-purple-500/15 p-2 text-purple-300">
                    <FileText className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-white">
                      {t('profilePage.spoolManagerImport.title')}
                    </h3>
                    <p className="mt-0.5 text-xs text-gray-400">
                      {file?.name}
                    </p>
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={close}
                disabled={isImporting}
                className="rounded-lg p-2 text-gray-400 transition hover:bg-white/10 hover:text-white disabled:opacity-40"
                aria-label={t('common.close')}
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="max-h-[70vh] overflow-y-auto p-5 md:p-6">
              {isPreviewing ? (
                <div className="flex min-h-52 flex-col items-center justify-center gap-3 text-gray-400">
                  <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
                  <p>{t('profilePage.spoolManagerImport.previewing')}</p>
                </div>
              ) : error ? (
                <div className="rounded-xl border border-red-500/25 bg-red-500/10 p-4 text-sm text-red-200">
                  {error}
                </div>
              ) : preview ? (
                <div className="space-y-4">
                  <p className="text-sm leading-relaxed text-gray-300">
                    {t('profilePage.spoolManagerImport.description')}
                  </p>

                  {preview.mapping_required && mapping ? (
                    <MappingEditor
                      columns={preview.available_columns}
                      sampleRows={preview.sample_rows}
                      mapping={mapping}
                      onChange={setMapping}
                    />
                  ) : (
                    <>
                      {preview.detected_label && (
                        <div className="inline-flex items-center gap-2 rounded-lg border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
                          <CheckCircle2 className="h-4 w-4" />
                          {t('profilePage.spoolManagerImport.detectedFormat', {
                            format: preview.detected_label,
                          })}
                        </div>
                      )}

                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                        <SummaryStat
                          value={preview.importable_rows}
                          label={t('profilePage.spoolManagerImport.ready')}
                          tone="purple"
                        />
                        <SummaryStat
                          value={preview.matched_rows}
                          label={t('profilePage.spoolManagerImport.matched')}
                          tone="green"
                        />
                        <SummaryStat
                          value={preview.unmatched_rows}
                          label={t('profilePage.spoolManagerImport.unmatched')}
                          tone="amber"
                        />
                        <SummaryStat
                          value={preview.duplicate_rows + preview.invalid_rows}
                          label={t('profilePage.spoolManagerImport.skipped')}
                          tone="gray"
                        />
                      </div>

                      {readyRows.length > 0 && (
                        <label className="flex cursor-pointer items-center gap-2 text-xs text-gray-300">
                          <input
                            type="checkbox"
                            checked={allReadySelected}
                            onChange={toggleAll}
                            className="h-4 w-4 rounded border-white/20 bg-white/10 accent-purple-500"
                          />
                          {t('profilePage.spoolManagerImport.selectAll')}
                        </label>
                      )}

                      <div className="space-y-2">
                        {preview.rows.map((row) => (
                          <ImportRow
                            key={`${row.row_number}-${row.fingerprint}`}
                            row={row}
                            selected={selected.has(row.fingerprint)}
                            onToggle={() => toggleRow(row)}
                          />
                        ))}
                      </div>
                    </>
                  )}
                </div>
              ) : null}
            </div>

            <div className="flex items-center justify-between gap-3 border-t border-white/10 px-5 py-4 md:px-6">
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                disabled={isImporting}
                className="text-sm text-gray-400 transition hover:text-white disabled:opacity-40"
              >
                {t('profilePage.spoolManagerImport.chooseAnother')}
              </button>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={close}
                  disabled={isImporting}
                  className="rounded-lg border border-white/15 px-4 py-2 text-sm text-gray-300 transition hover:bg-white/10 disabled:opacity-40"
                >
                  {t('common.cancel')}
                </button>
                {preview?.mapping_required ? (
                  <button
                    type="button"
                    onClick={() => void applyMapping()}
                    disabled={!canApplyMapping || isImporting || isPreviewing}
                    className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-purple-600 to-pink-600 px-4 py-2 text-sm font-medium text-white transition hover:from-purple-500 hover:to-pink-500 disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    {isPreviewing && <Loader2 className="h-4 w-4 animate-spin" />}
                    {t('profilePage.spoolManagerImport.applyMapping')}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => void runImport()}
                    disabled={!preview || selected.size === 0 || isImporting || isPreviewing}
                    className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-purple-600 to-pink-600 px-4 py-2 text-sm font-medium text-white transition hover:from-purple-500 hover:to-pink-500 disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    {isImporting && <Loader2 className="h-4 w-4 animate-spin" />}
                    {t('profilePage.spoolManagerImport.importSelected', { count: selected.size })}
                  </button>
                )}
              </div>
            </div>
          </div>
        </ModalOverlay>
      )}
    </>
  );
};

/** @deprecated Use the provider-neutral SpoolImportButton name. */
export const SpoolManagerImportButton = SpoolImportButton;

const CORE_MAPPING_FIELDS: SpoolImportSemanticField[] = [
  'spool_name',
  'vendor',
  'material',
  'color_name',
  'color_hex',
  'serial_number',
  'initial_weight',
  'remaining_weight',
  'used_weight',
  'empty_spool_weight',
  'price',
  'currency',
  'note',
];

const ADVANCED_MAPPING_FIELDS: SpoolImportSemanticField[] = [
  'density',
  'diameter',
  'diameter_tolerance',
  'flow_rate_compensation',
  'nozzle_temperature',
  'bed_temperature',
  'enclosure_temperature',
  'nozzle_temperature_offset',
  'bed_temperature_offset',
  'enclosure_temperature_offset',
  'total_length',
  'used_length',
  'first_use',
  'last_use',
  'purchased_from',
  'purchased_on',
];

const WEIGHT_MAPPING_FIELDS = new Set<SpoolImportSemanticField>([
  'initial_weight',
  'remaining_weight',
  'used_weight',
  'empty_spool_weight',
]);
const LENGTH_MAPPING_FIELDS = new Set<SpoolImportSemanticField>([
  'total_length',
  'used_length',
]);

const MappingEditor: React.FC<{
  columns: string[];
  sampleRows: Array<Record<string, string>>;
  mapping: SpoolImportColumnMapping;
  onChange: (mapping: SpoolImportColumnMapping) => void;
}> = ({ columns, sampleRows, mapping, onChange }) => {
  const { t } = useTranslation();

  const updateField = (field: SpoolImportSemanticField, column: string) => {
    const fields = { ...mapping.fields };
    const units = { ...mapping.units };
    if (column) {
      fields[field] = column;
      if (WEIGHT_MAPPING_FIELDS.has(field) && !units[field]) units[field] = 'g';
      if (LENGTH_MAPPING_FIELDS.has(field) && !units[field]) units[field] = 'mm';
    } else {
      delete fields[field];
      delete units[field];
    }
    onChange({ fields, units });
  };

  const updateUnit = (field: SpoolImportSemanticField, unit: SpoolImportUnit) => {
    onChange({ ...mapping, units: { ...mapping.units, [field]: unit } });
  };

  const renderField = (field: SpoolImportSemanticField) => {
    const column = mapping.fields[field] ?? '';
    const sample = column ? sampleRows[0]?.[column] : null;
    const isWeight = WEIGHT_MAPPING_FIELDS.has(field);
    const isLength = LENGTH_MAPPING_FIELDS.has(field);
    const units: SpoolImportUnit[] = isWeight ? ['g', 'kg'] : ['mm', 'm'];
    return (
      <div
        key={field}
        className="grid gap-2 rounded-xl border border-white/10 bg-white/[0.035] p-3 sm:grid-cols-[minmax(0,0.85fr)_minmax(0,1.25fr)_auto] sm:items-center"
      >
        <div>
          <div className="text-sm text-gray-200">
            {t(`profilePage.spoolManagerImport.mappingFields.${field}`)}
          </div>
          {field === 'initial_weight' && (
            <div className="mt-0.5 text-[11px] text-purple-300">
              {t('profilePage.spoolManagerImport.weightRequiredHint')}
            </div>
          )}
        </div>
        <div className="min-w-0">
          <select
            value={column}
            onChange={(event) => updateField(field, event.target.value)}
            className="w-full rounded-lg border border-white/15 bg-slate-900 px-3 py-2 text-sm text-gray-100 outline-none transition focus:border-purple-400/60"
          >
            <option value="">
              {t('profilePage.spoolManagerImport.notMapped')}
            </option>
            {columns.map((candidate) => (
              <option
                key={candidate}
                value={candidate}
                disabled={Object.entries(mapping.fields).some(
                  ([otherField, selectedColumn]) =>
                    otherField !== field && selectedColumn === candidate,
                )}
              >
                {candidate}
              </option>
            ))}
          </select>
          {sample && (
            <div className="mt-1 truncate text-[11px] text-gray-500">
              {t('profilePage.spoolManagerImport.sampleValue', { value: sample })}
            </div>
          )}
        </div>
        {(isWeight || isLength) && column ? (
          <select
            value={mapping.units[field] ?? (isWeight ? 'g' : 'mm')}
            onChange={(event) =>
              updateUnit(field, event.target.value as SpoolImportUnit)
            }
            className="rounded-lg border border-white/15 bg-slate-900 px-2.5 py-2 text-sm text-gray-100 outline-none transition focus:border-purple-400/60"
          >
            {units.map((unit) => (
              <option key={unit} value={unit}>
                {unit}
              </option>
            ))}
          </select>
        ) : (
          <span />
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-amber-400/20 bg-amber-500/10 p-4">
        <div className="flex gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" />
          <div>
            <div className="text-sm font-medium text-amber-100">
              {t('profilePage.spoolManagerImport.mappingTitle')}
            </div>
            <p className="mt-1 text-xs leading-relaxed text-amber-100/70">
              {t('profilePage.spoolManagerImport.mappingDescription')}
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-2">{CORE_MAPPING_FIELDS.map(renderField)}</div>

      <details className="rounded-xl border border-white/10 bg-white/[0.025]">
        <summary className="cursor-pointer px-4 py-3 text-sm text-gray-200">
          {t('profilePage.spoolManagerImport.advancedMapping')}
        </summary>
        <div className="space-y-2 border-t border-white/10 p-3">
          {ADVANCED_MAPPING_FIELDS.map(renderField)}
        </div>
      </details>
    </div>
  );
};

const SummaryStat: React.FC<{
  value: number;
  label: string;
  tone: 'purple' | 'green' | 'amber' | 'gray';
}> = ({ value, label, tone }) => {
  const tones = {
    purple: 'border-purple-400/20 bg-purple-500/10 text-purple-200',
    green: 'border-emerald-400/20 bg-emerald-500/10 text-emerald-200',
    amber: 'border-amber-400/20 bg-amber-500/10 text-amber-200',
    gray: 'border-white/10 bg-white/5 text-gray-300',
  };
  return (
    <div className={`rounded-xl border p-3 ${tones[tone]}`}>
      <div className="text-lg font-semibold">{value}</div>
      <div className="text-[11px] opacity-75">{label}</div>
    </div>
  );
};

const ImportRow: React.FC<{
  row: SpoolManagerPreviewRow;
  selected: boolean;
  onToggle: () => void;
}> = ({ row, selected, onToggle }) => {
  const { t } = useTranslation();
  const disabled = row.status !== 'ready';
  const warning = row.warnings[0];
  return (
    <label
      className={`grid w-full grid-cols-[auto_minmax(0,1fr)] gap-3 rounded-xl border p-3 text-left transition md:grid-cols-[auto_minmax(0,1.25fr)_minmax(0,1fr)_auto] md:items-center ${
        selected
          ? 'border-purple-400/45 bg-purple-500/10'
          : disabled
          ? 'cursor-default border-white/5 bg-white/[0.025] opacity-60'
          : 'border-white/10 bg-white/[0.035] hover:border-white/20 hover:bg-white/[0.06]'
      }`}
    >
      <input
        type="checkbox"
        checked={selected}
        disabled={disabled}
        onChange={onToggle}
        className="mt-1 h-4 w-4 rounded border-white/20 bg-white/10 accent-purple-500 md:mt-0"
      />
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          {row.color_hex && (
            <span
              className="h-3.5 w-3.5 shrink-0 rounded-full border border-white/30"
              style={{ backgroundColor: row.color_hex }}
            />
          )}
          <span className="truncate text-sm font-medium text-white">{row.spool_name}</span>
        </div>
        <p className="mt-0.5 truncate text-xs text-gray-400">
          {[row.vendor, row.material, row.color_name].filter(Boolean).join(' · ') || '—'}
        </p>
      </div>
      <div className="col-start-2 min-w-0 md:col-start-auto">
        {row.suggested_filament ? (
          <div className="flex items-start gap-2 text-xs text-emerald-300">
            <Link2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="truncate">
              {row.suggested_filament.brand_name} · {row.suggested_filament.name}
            </span>
          </div>
        ) : row.status === 'ready' ? (
          <div className="flex items-start gap-2 text-xs text-amber-300">
            <Unlink className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{t('profilePage.spoolManagerImport.withoutCatalogLink')}</span>
          </div>
        ) : (
          <div className="flex items-start gap-2 text-xs text-gray-400">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{warning ? t(rowWarningKey(warning)) : row.status}</span>
          </div>
        )}
      </div>
      <div className="col-start-2 text-xs text-gray-300 md:col-start-auto md:text-right">
        {row.remaining_weight_g != null && row.initial_weight_g != null ? (
          <>
            <div className="font-medium text-white">{row.remaining_weight_g.toFixed(0)} г</div>
            <div className="text-[11px] text-gray-500">/ {row.initial_weight_g.toFixed(0)} г</div>
          </>
        ) : (
          <CheckCircle2 className="h-4 w-4 text-gray-500" />
        )}
      </div>
    </label>
  );
};
