import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { physicalPrintersAPI, type PhysicalPrinter, type PrinterSuggestion } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { Dropdown } from './Dropdown';

function SuggestionCard({
  suggestion,
  confirmed,
}: {
  suggestion: PrinterSuggestion;
  confirmed: PhysicalPrinter[];
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [mergeTarget, setMergeTarget] = useState('');
  const refresh = async () => {
    await Promise.all(['printer-suggestions', 'physical-printers', 'printer-bindings', 'devices']
      .map((key) => client.invalidateQueries({ queryKey: [key] })));
  };
  const confirm = useMutation({
    mutationFn: () => physicalPrintersAPI.confirm(suggestion.id),
    onSuccess: refresh,
  });
  const dismiss = useMutation({
    mutationFn: () => physicalPrintersAPI.dismiss(suggestion.id),
    onSuccess: refresh,
  });
  const merge = useMutation({
    mutationFn: async () => {
      const targetId = Number(mergeTarget);
      const preview = await physicalPrintersAPI.previewMerge(suggestion.id, targetId);
      if (!preview.allowed) throw new Error(preview.reason ?? 'merge_refused');
      await physicalPrintersAPI.merge(suggestion.id, targetId, preview.revision);
    },
    onSuccess: refresh,
  });
  const busy = confirm.isPending || dismiss.isPending || merge.isPending;
  const sameModel = new Set(suggestion.same_model_printer_ids);
  const options = [...confirmed]
    .sort((a, b) => Number(sameModel.has(b.id)) - Number(sameModel.has(a.id)))
    .map((printer) => ({ value: String(printer.id), label: `${printer.name} · #${printer.id}` }));
  const failure = confirm.error ?? dismiss.error ?? merge.error;
  const detail = (failure as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail;

  return (
    <div className="min-w-0 space-y-2 rounded-lg border border-white/10 bg-white/5 p-3">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-white" title={suggestion.name}>{suggestion.name}</p>
        {(suggestion.catalog_printer_name || suggestion.profile_names.length > 0) && (
          <p className="truncate text-xs text-gray-400">
            {[suggestion.catalog_printer_name, suggestion.profile_names.slice(0, 2).join(', ')]
              .filter(Boolean).join(' · ')}
          </p>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={busy} onClick={() => confirm.mutate()}
          className="rounded-lg bg-purple-600 px-3 py-1.5 text-xs text-white disabled:opacity-50">
          {t('printerSuggestions.mine')}
        </button>
        <button type="button" disabled={busy} onClick={() => dismiss.mutate()}
          className="rounded-lg border border-white/20 px-3 py-1.5 text-xs text-gray-300 transition-colors hover:bg-white/10 disabled:opacity-50">
          {t('printerSuggestions.hide')}
        </button>
      </div>
      {options.length > 0 && (
        <div className="flex items-center gap-2">
          <Dropdown size="sm" className="min-w-0 flex-1" value={mergeTarget} options={options}
            onChange={(value) => setMergeTarget(String(value))}
            placeholder={t('printerSuggestions.sameAs')} />
          <button type="button" disabled={!mergeTarget || busy} onClick={() => merge.mutate()}
            className="shrink-0 rounded-lg border border-white/20 px-3 py-1.5 text-xs text-white transition-colors hover:bg-white/10 disabled:opacity-50">
            {t('printerSuggestions.merge')}
          </button>
        </div>
      )}
      {failure && (
        <p className="text-xs text-red-300">
          {translateApiError(t, detail, t('printerSuggestions.error'))}
        </p>
      )}
    </div>
  );
}

export function PrinterSuggestions({
  confirmed,
  userId,
}: {
  confirmed: PhysicalPrinter[];
  userId: number | null | undefined;
}) {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: ['printer-suggestions', userId],
    queryFn: physicalPrintersAPI.suggestions,
    staleTime: 30_000,
    enabled: userId != null,
  });
  const items = query.data ?? [];
  if (items.length === 0) return null;
  return (
    <section className="space-y-3 rounded-xl border border-cyan-400/20 bg-cyan-500/5 p-4">
      <div>
        <h4 className="font-semibold text-cyan-100">{t('printerSuggestions.title', { count: items.length })}</h4>
        <p className="text-xs text-gray-400">{t('printerSuggestions.hint')}</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {items.map((suggestion) => (
          <SuggestionCard key={suggestion.id} suggestion={suggestion} confirmed={confirmed} />
        ))}
      </div>
    </section>
  );
}
