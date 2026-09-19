import { useState } from 'react';
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { AxiosError } from 'axios';
import { physicalPrintersAPI, type PendingPrinterConnection, type PhysicalPrinter } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { Dropdown } from './Dropdown';
import { physicalPrinterQueryKeys } from '../utils/physicalPrinterQueries';

function isMissingCandidate(error: unknown): boolean {
  return (error as AxiosError | null)?.response?.status === 404;
}

function ConnectionChoice({
  connection,
  printers,
  candidateLookupPending,
  candidateLookupError,
  onRetryCandidateLookup,
}: {
  connection: PendingPrinterConnection;
  printers: PhysicalPrinter[];
  candidateLookupPending: boolean;
  candidateLookupError: boolean;
  onRetryCandidateLookup: () => void;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [target, setTarget] = useState('');
  const mutation = useMutation({
    mutationFn: () => physicalPrintersAPI.resolveConnection(
      connection.id, target === 'new' ? null : Number(target), connection.revision,
    ),
    onSuccess: async () => {
      await Promise.all(['printer-connections-pending', 'printer-bindings', 'physical-printers', 'devices']
        .map((key) => client.invalidateQueries({ queryKey: [key] })));
    },
    onError: () => client.invalidateQueries({ queryKey: ['printer-connections-pending'] }),
  });
  const error = mutation.error as AxiosError<{ detail: unknown }> | null;
  const options = [...printers]
    .sort((a, b) => Number(connection.candidate_printer_ids.includes(b.id))
      - Number(connection.candidate_printer_ids.includes(a.id)))
    .map((printer) => ({ value: String(printer.id), label: `${printer.name} · #${printer.id}` }));
  options.push({ value: 'new', label: t('printerConnections.newDevice') });
  const connectionName = connection.preset_name ?? connection.provider;
  return (
    <div className="min-w-0 space-y-2 rounded-lg border border-amber-400/20 p-3">
      <p className="truncate text-sm text-white" title={connectionName ?? undefined}>{connectionName}</p>
      <div className="flex items-center gap-2">
        <Dropdown size="sm" className="min-w-0 flex-1" value={target} options={options}
          onChange={(value) => setTarget(String(value))}
          placeholder={t('printerConnections.choose')}
          disabled={candidateLookupPending || candidateLookupError} />
        <button type="button"
          disabled={!target || mutation.isPending || candidateLookupPending || candidateLookupError}
          onClick={() => mutation.mutate()}
          className="shrink-0 whitespace-nowrap rounded-lg bg-purple-600 px-3 py-1.5 text-sm text-white disabled:opacity-50">
          {t('printerConnections.confirm')}
        </button>
      </div>
      {candidateLookupError && (
        <button type="button" onClick={onRetryCandidateLookup} className="text-sm text-amber-300">
          {t('printerConnections.retry')}
        </button>
      )}
      {error && <p role="alert" className="text-sm text-rose-300">{
        translateApiError(t, error.response?.data?.detail, t('printerConnections.failed'))
      }</p>}
    </div>
  );
}

export function PrinterConnectionReview({
  printers,
  userId,
}: {
  printers: PhysicalPrinter[];
  userId: number | null | undefined;
}) {
  const { t } = useTranslation();
  const { data = [], isError, refetch } = useQuery({
    queryKey: ['printer-connections-pending'], queryFn: physicalPrintersAPI.pendingConnections,
  });
  const visibleIds = new Set(printers.map((printer) => printer.id));
  const missingCandidateIds = Array.from(
    new Set(data.flatMap((connection) => connection.candidate_printer_ids)),
  ).filter((printerId) => !visibleIds.has(printerId));
  const candidateQueries = useQueries({
    queries: missingCandidateIds.map((printerId) => ({
      queryKey: physicalPrinterQueryKeys.lookup(userId, printerId),
      queryFn: ({ signal }: { signal: AbortSignal }) => physicalPrintersAPI.get(printerId, signal),
      enabled: userId != null,
      staleTime: 30_000,
    })),
  });
  const candidateQueryById = new Map(
    missingCandidateIds.map((printerId, index) => [printerId, candidateQueries[index]]),
  );
  const knownPrinters = [...printers];
  const knownIds = new Set(visibleIds);
  for (const query of candidateQueries) {
    if (query.data && !knownIds.has(query.data.id)) {
      knownIds.add(query.data.id);
      knownPrinters.push(query.data);
    }
  }
  if (isError) return <button type="button" onClick={() => void refetch()} className="text-sm text-amber-300">
    {t('printerConnections.retry')}
  </button>;
  if (!data.length) return null;
  return (
    <section className="space-y-3 rounded-xl border border-amber-400/30 bg-amber-500/5 p-4">
      <h4 className="font-semibold text-amber-200">{t('printerConnections.title')}</h4>
      <p className="text-sm text-gray-300">{t('printerConnections.hint')}</p>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {data.map((connection) => {
          const lookups = connection.candidate_printer_ids
            .filter((printerId) => !visibleIds.has(printerId))
            .map((printerId) => candidateQueryById.get(printerId))
            .filter((query) => query !== undefined);
          return (
            <ConnectionChoice
              key={`${connection.id}-${connection.revision}`}
              connection={connection}
              printers={knownPrinters}
              candidateLookupPending={lookups.some((query) => query.isPending)}
              candidateLookupError={lookups.some(
                (query) => query.isError && !isMissingCandidate(query.error),
              )}
              onRetryCandidateLookup={() => {
                void Promise.all(
                  lookups
                    .filter((query) => query.isError && !isMissingCandidate(query.error))
                    .map((query) => query.refetch()),
                );
              }}
            />
          );
        })}
      </div>
    </section>
  );
}
