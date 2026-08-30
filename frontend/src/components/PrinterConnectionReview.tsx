import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { AxiosError } from 'axios';
import { physicalPrintersAPI, type PendingPrinterConnection, type PhysicalPrinter } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { Dropdown } from './Dropdown';

function ConnectionChoice({ connection, printers }: {
  connection: PendingPrinterConnection; printers: PhysicalPrinter[];
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
  return (
    <div className="space-y-2 rounded-lg border border-amber-400/20 p-3">
      <p className="text-sm text-white">{connection.preset_name ?? connection.provider}</p>
      <Dropdown size="sm" value={target} options={options} onChange={(value) => setTarget(String(value))}
        placeholder={t('printerConnections.choose')} />
      <button type="button" disabled={!target || mutation.isPending} onClick={() => mutation.mutate()}
        className="rounded-lg bg-purple-600 px-3 py-2 text-sm text-white disabled:opacity-50">
        {t('printerConnections.confirm')}
      </button>
      {error && <p role="alert" className="text-sm text-rose-300">{
        translateApiError(t, error.response?.data?.detail, t('printerConnections.failed'))
      }</p>}
    </div>
  );
}

export function PrinterConnectionReview({ printers }: { printers: PhysicalPrinter[] }) {
  const { t } = useTranslation();
  const { data = [], isError, refetch } = useQuery({
    queryKey: ['printer-connections-pending'], queryFn: physicalPrintersAPI.pendingConnections,
  });
  if (isError) return <button type="button" onClick={() => void refetch()} className="text-sm text-amber-300">
    {t('printerConnections.retry')}
  </button>;
  if (!data.length) return null;
  return (
    <section className="space-y-3 rounded-xl border border-amber-400/30 bg-amber-500/5 p-4">
      <h4 className="font-semibold text-amber-200">{t('printerConnections.title')}</h4>
      <p className="text-sm text-gray-300">{t('printerConnections.hint')}</p>
      {data.map((connection) => <ConnectionChoice key={`${connection.id}-${connection.revision}`} connection={connection} printers={printers} />)}
    </section>
  );
}
