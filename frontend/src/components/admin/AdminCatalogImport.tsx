import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Loader2,
  RotateCcw,
  Upload,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { AxiosError } from 'axios';

import { adminCatalogImportAPI } from '../../api/client';
import type {
  CatalogImportDraft,
  CatalogImportPlanRow,
  CatalogImportPreview,
  CatalogImportSheet,
} from '../../types/api';
import { translateApiError } from '../../utils/translateApiError';
import { toast } from '../Toast';

const SHEETS: Array<{
  id: CatalogImportSheet;
  backendName: CatalogImportPlanRow['sheet'];
  labelKey: string;
}> = [
  { id: 'brands', backendName: 'Brands', labelKey: 'brands' },
  { id: 'filaments', backendName: 'Filaments', labelKey: 'filaments' },
  { id: 'brand_markets', backendName: 'BrandMarkets', labelKey: 'brandMarkets' },
  { id: 'filament_markets', backendName: 'FilamentMarkets', labelKey: 'filamentMarkets' },
  { id: 'presets', backendName: 'Presets', labelKey: 'presets' },
];

const PAGE_SIZE = 40;

function cellText(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function AdminCatalogImport() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<CatalogImportPreview | null>(null);
  const [draft, setDraft] = useState<CatalogImportDraft | null>(null);
  const [activeSheet, setActiveSheet] = useState<CatalogImportSheet>('brands');
  const [page, setPage] = useState(1);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const historyQuery = useQuery({
    queryKey: ['admin-catalog-import-history'],
    queryFn: adminCatalogImportAPI.history,
  });

  const templateMutation = useMutation({
    mutationFn: adminCatalogImportAPI.downloadTemplate,
    onSuccess: (blob) => downloadBlob(blob, 'filamenthub-catalog-import.xlsx'),
    onError: () => toast.error(t('adminCatalogImport.templateError')),
  });

  const uploadMutation = useMutation({
    mutationFn: adminCatalogImportAPI.previewWorkbook,
    onSuccess: (result) => {
      setPreview(result);
      setDraft(result.draft);
      setDirty(false);
      setError(null);
      const firstPopulated = SHEETS.find((sheet) => result.draft[sheet.id].length > 0);
      setActiveSheet(firstPopulated?.id ?? 'brands');
      setPage(1);
    },
    onError: (requestError: AxiosError<{ detail: unknown }>) => {
      setError(
        translateApiError(
          t,
          requestError.response?.data?.detail,
          t('adminCatalogImport.previewError'),
        ),
      );
    },
  });

  const revalidateMutation = useMutation({
    mutationFn: adminCatalogImportAPI.previewDraft,
    onSuccess: (result) => {
      setPreview(result);
      setDraft(result.draft);
      setDirty(false);
      setError(null);
    },
    onError: (requestError: AxiosError<{ detail: unknown }>) => {
      setError(
        translateApiError(
          t,
          requestError.response?.data?.detail,
          t('adminCatalogImport.previewError'),
        ),
      );
    },
  });

  const applyMutation = useMutation({
    mutationFn: ({ value, token }: { value: CatalogImportDraft; token: string }) =>
      adminCatalogImportAPI.apply(value, token),
    onSuccess: (result) => {
      toast.success(t('adminCatalogImport.applied', { id: result.batch_id }));
      setPreview(null);
      setDraft(null);
      setDirty(false);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ['admin-catalog-import-history'] });
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] });
      queryClient.invalidateQueries({ queryKey: ['admin-brands'] });
      queryClient.invalidateQueries({ queryKey: ['admin-filaments'] });
      queryClient.invalidateQueries({ queryKey: ['admin-presets'] });
    },
    onError: (requestError: AxiosError<{ detail: unknown }>) => {
      setError(
        translateApiError(
          t,
          requestError.response?.data?.detail,
          t('adminCatalogImport.applyError'),
        ),
      );
    },
  });

  const activeDefinition = SHEETS.find((sheet) => sheet.id === activeSheet) ?? SHEETS[0];
  const activeRows = draft?.[activeSheet] ?? [];
  const columns = useMemo(() => {
    const ordered: string[] = [];
    for (const row of activeRows) {
      for (const key of Object.keys(row)) {
        if (key !== '_row' && !ordered.includes(key)) ordered.push(key);
      }
    }
    return ordered;
  }, [activeRows]);
  const totalPages = Math.max(1, Math.ceil(activeRows.length / PAGE_SIZE));
  const visibleRows = activeRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const planByRow = useMemo(() => {
    const map = new Map<number, CatalogImportPlanRow>();
    for (const row of preview?.rows ?? []) {
      if (row.sheet === activeDefinition.backendName) map.set(row.row, row);
    }
    return map;
  }, [activeDefinition.backendName, preview?.rows]);

  const updateCell = (visibleIndex: number, column: string, value: unknown) => {
    if (!draft) return;
    const absoluteIndex = (page - 1) * PAGE_SIZE + visibleIndex;
    const nextRows = draft[activeSheet].map((row, rowIndex) =>
      rowIndex === absoluteIndex ? { ...row, [column]: value } : row,
    );
    setDraft({ ...draft, [activeSheet]: nextRows });
    setDirty(true);
  };

  const cancel = () => {
    setPreview(null);
    setDraft(null);
    setDirty(false);
    setError(null);
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <header>
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-indigo-300">
          <FileSpreadsheet className="h-4 w-4" />
          {t('adminCatalogImport.eyebrow')}
        </div>
        <h2 className="text-2xl font-bold text-white">{t('adminCatalogImport.title')}</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
          {t('adminCatalogImport.description')}
        </p>
      </header>

      {!draft && (
        <section className="grid gap-4 md:grid-cols-2">
          <button
            type="button"
            onClick={() => templateMutation.mutate()}
            disabled={templateMutation.isPending}
            className="flex items-center gap-3 rounded-2xl border border-indigo-400/20 bg-indigo-500/10 p-5 text-left transition hover:bg-indigo-500/15 disabled:opacity-50"
          >
            <Download className="h-6 w-6 text-indigo-300" />
            <span>
              <span className="block font-semibold text-white">{t('adminCatalogImport.downloadTemplate')}</span>
              <span className="mt-1 block text-xs text-gray-400">{t('adminCatalogImport.templateHint')}</span>
            </span>
          </button>
          <label className="flex cursor-pointer items-center gap-3 rounded-2xl border border-cyan-400/20 bg-cyan-500/10 p-5 transition hover:bg-cyan-500/15">
            {uploadMutation.isPending ? (
              <Loader2 className="h-6 w-6 animate-spin text-cyan-300" />
            ) : (
              <Upload className="h-6 w-6 text-cyan-300" />
            )}
            <span>
              <span className="block font-semibold text-white">{t('adminCatalogImport.upload')}</span>
              <span className="mt-1 block text-xs text-gray-400">{t('adminCatalogImport.uploadHint')}</span>
            </span>
            <input
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="sr-only"
              disabled={uploadMutation.isPending}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) uploadMutation.mutate(file);
                event.target.value = '';
              }}
            />
          </label>
        </section>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {draft && preview && (
        <>
          <section className="rounded-2xl border border-white/10 bg-black/15 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="font-semibold text-white">{draft.filename}</div>
                <div className="mt-1 text-xs text-gray-400">{t('adminCatalogImport.noWriteBeforeApply')}</div>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                {(['create', 'update', 'noop', 'skipped', 'error'] as const).map((status) => (
                  <span
                    key={status}
                    className={`rounded-full px-2.5 py-1 font-semibold ${
                      status === 'error'
                        ? 'bg-red-500/15 text-red-300'
                        : status === 'create'
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : status === 'update'
                            ? 'bg-blue-500/15 text-blue-300'
                            : 'bg-white/10 text-gray-300'
                    }`}
                  >
                    {t(`adminCatalogImport.status.${status}`)}: {preview.summary[status]}
                  </span>
                ))}
              </div>
            </div>
          </section>

          <nav className="flex flex-wrap gap-2">
            {SHEETS.map((sheet) => (
              <button
                key={sheet.id}
                type="button"
                onClick={() => {
                  setActiveSheet(sheet.id);
                  setPage(1);
                }}
                className={`rounded-lg px-3 py-2 text-xs font-semibold transition ${
                  activeSheet === sheet.id
                    ? 'bg-indigo-500 text-white'
                    : 'bg-white/5 text-gray-300 hover:bg-white/10'
                }`}
              >
                {t(`adminCatalogImport.sheets.${sheet.labelKey}`)} · {draft[sheet.id].length}
              </button>
            ))}
          </nav>

          {activeRows.length === 0 ? (
            <div className="rounded-xl border border-dashed border-white/15 py-10 text-center text-sm text-gray-500">
              {t('adminCatalogImport.emptySheet')}
            </div>
          ) : (
            <section className="overflow-hidden rounded-xl border border-white/10">
              <div className="max-h-[58vh] overflow-auto">
                <table className="min-w-max border-collapse text-xs">
                  <thead className="sticky top-0 z-10 bg-gray-950">
                    <tr>
                      <th className="border-b border-r border-white/10 px-2 py-2 text-left text-gray-400">#</th>
                      <th className="border-b border-r border-white/10 px-2 py-2 text-left text-gray-400">{t('adminCatalogImport.result')}</th>
                      {columns.map((column) => (
                        <th key={column} className="border-b border-r border-white/10 px-2 py-2 text-left font-medium text-gray-300">
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRows.map((row, visibleIndex) => {
                      const rowNumber = Number(row._row ?? (page - 1) * PAGE_SIZE + visibleIndex + 2);
                      const result = planByRow.get(rowNumber);
                      return (
                        <tr key={`${rowNumber}-${visibleIndex}`} className={result?.status === 'error' ? 'bg-red-500/5' : 'odd:bg-white/[0.02]'}>
                          <td className="border-b border-r border-white/10 px-2 py-2 font-mono text-gray-500">{rowNumber}</td>
                          <td className="max-w-64 border-b border-r border-white/10 px-2 py-2">
                            <span className={result?.status === 'error' ? 'text-red-300' : 'text-gray-300'}>
                              {result ? t(`adminCatalogImport.status.${result.status}`) : '—'}
                            </span>
                            {result?.message && <div className="mt-1 whitespace-normal text-[11px] leading-4 text-red-300">{result.message}</div>}
                          </td>
                          {columns.map((column) => {
                            const checkbox = column === 'enabled' || column === 'overwrite';
                            return (
                              <td key={column} className="border-b border-r border-white/10 p-1">
                                {checkbox ? (
                                  <input
                                    type="checkbox"
                                    checked={['true', '1', 'yes', 'да'].includes(cellText(row[column]).toLowerCase())}
                                    onChange={(event) => updateCell(visibleIndex, column, event.target.checked)}
                                    className="h-4 w-4 accent-indigo-500"
                                  />
                                ) : (
                                  <input
                                    value={cellText(row[column])}
                                    onChange={(event) => updateCell(visibleIndex, column, event.target.value)}
                                    className="w-40 rounded border border-transparent bg-transparent px-2 py-1.5 text-gray-200 outline-none transition focus:border-indigo-400/50 focus:bg-black/30"
                                  />
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-3 border-t border-white/10 p-3 text-xs text-gray-400">
                  <button type="button" disabled={page === 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="rounded bg-white/5 px-3 py-1.5 disabled:opacity-30">
                    ←
                  </button>
                  {page} / {totalPages}
                  <button type="button" disabled={page === totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))} className="rounded bg-white/5 px-3 py-1.5 disabled:opacity-30">
                    →
                  </button>
                </div>
              )}
            </section>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-black/15 p-4">
            <button type="button" onClick={cancel} className="inline-flex items-center gap-2 rounded-lg border border-white/15 px-4 py-2 text-sm text-gray-300 transition hover:bg-white/5">
              <RotateCcw className="h-4 w-4" />
              {t('adminCatalogImport.cancel')}
            </button>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={!dirty || revalidateMutation.isPending}
                onClick={() => draft && revalidateMutation.mutate(draft)}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
              >
                {revalidateMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                {t('adminCatalogImport.revalidate')}
              </button>
              <button
                type="button"
                disabled={dirty || !preview.confirmation_token || preview.summary.error > 0 || applyMutation.isPending}
                onClick={() => {
                  if (draft && preview.confirmation_token) {
                    applyMutation.mutate({ value: draft, token: preview.confirmation_token });
                  }
                }}
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-bold text-slate-950 disabled:opacity-40"
              >
                {applyMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                {t('adminCatalogImport.apply')}
              </button>
            </div>
          </div>
        </>
      )}

      <section>
        <h3 className="mb-3 text-sm font-semibold text-white">{t('adminCatalogImport.history')}</h3>
        <div className="space-y-2">
          {(historyQuery.data?.items ?? []).map((batch) => (
            <div key={batch.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-xs">
              <div>
                <span className="font-semibold text-gray-200">#{batch.id} · {batch.filename}</span>
                <span className="ml-2 text-gray-500">{new Date(batch.applied_at).toLocaleString()}</span>
              </div>
              <div className="text-gray-400">
                +{batch.summary.create ?? 0} · Δ{batch.summary.update ?? 0}
              </div>
            </div>
          ))}
          {!historyQuery.isLoading && (historyQuery.data?.items.length ?? 0) === 0 && (
            <div className="text-sm text-gray-500">{t('adminCatalogImport.noHistory')}</div>
          )}
        </div>
      </section>
    </div>
  );
}
