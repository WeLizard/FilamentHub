import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Copy,
  RefreshCw,
  RotateCcw,
  ScanSearch,
  Search,
} from 'lucide-react';

import { adminAPI } from '../../api/client';
import { toast } from '../Toast';
import type {
  OrcaPresetScope,
  OrcaSchemaObservationStatus,
} from '../../types/api';

const PAGE_SIZE = 25;

export function AdminOrcaSchemaObservations() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<OrcaSchemaObservationStatus | 'all'>('new');
  const [scope, setScope] = useState<OrcaPresetScope | 'all'>('all');
  const [search, setSearch] = useState('');

  const query = useQuery({
    queryKey: ['admin-orca-schema-observations', page, status, scope, search],
    queryFn: () => adminAPI.listOrcaSchemaObservations({
      page,
      size: PAGE_SIZE,
      status: status === 'all' ? undefined : status,
      scope: scope === 'all' ? undefined : scope,
      search: search.trim() || undefined,
    }),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, nextStatus }: { id: number; nextStatus: OrcaSchemaObservationStatus }) =>
      adminAPI.updateOrcaSchemaObservation(id, nextStatus),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-orca-schema-observations'] });
      queryClient.invalidateQueries({ queryKey: ['admin-orca-schema-count'] });
    },
  });

  const data = query.data;
  const registryDigest = data?.registry_version.split(':').at(-1)?.slice(0, 12) ?? '—';
  const setFilter = <T,>(setter: (value: T) => void, value: T) => {
    setter(value);
    setPage(1);
  };
  const copyObservation = async (item: NonNullable<typeof data>['items'][number]) => {
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error('Clipboard API is unavailable');
      }
      await navigator.clipboard.writeText(JSON.stringify({
        field_name: item.field_name,
        preset_scope: item.scope,
        value_shape: item.value_shape,
        occurrences: item.occurrences,
        first_seen_at: item.first_seen_at,
        last_seen_at: item.last_seen_at,
        first_source: item.first_source,
        last_source: item.last_source,
        registry_version: item.registry_version,
      }, null, 2));
      toast.success(t('adminOrcaSchema.copied'));
    } catch {
      toast.error(t('adminOrcaSchema.copyError'));
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="rounded-xl border border-cyan-400/20 bg-cyan-400/10 p-2.5">
            <ScanSearch className="h-6 w-6 text-cyan-300" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-bold text-white">{t('adminOrcaSchema.title')}</h2>
              {(data?.new_count ?? 0) > 0 && (
                <span className="rounded-full border border-amber-400/25 bg-amber-400/10 px-2.5 py-1 text-xs font-semibold text-amber-300">
                  {t('adminOrcaSchema.newCount', { count: data?.new_count })}
                </span>
              )}
            </div>
            <p className="mt-1 max-w-3xl text-sm text-gray-400">
              {t('adminOrcaSchema.description')}
            </p>
            <p className="mt-2 max-w-3xl text-xs text-gray-500">
              {t('adminOrcaSchema.queueHint')}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 self-start rounded-lg border border-white/10 bg-black/15 px-3 py-2 text-xs text-gray-400">
          <span>{t('adminOrcaSchema.registry')}</span>
          <code className="text-cyan-300">{registryDigest}</code>
          <button
            type="button"
            onClick={() => query.refetch()}
            className="rounded p-1 text-gray-400 transition-colors hover:bg-white/10 hover:text-white"
            title={t('adminOrcaSchema.refresh')}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${query.isFetching ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="grid gap-3 rounded-xl border border-white/10 bg-black/10 p-3 md:grid-cols-[minmax(0,1fr)_180px_180px]">
        <label className="relative block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
          <input
            value={search}
            onChange={(event) => setFilter(setSearch, event.target.value)}
            placeholder={t('adminOrcaSchema.search')}
            className="w-full rounded-lg border border-white/10 bg-white/5 py-2 pl-9 pr-3 text-sm text-white outline-none transition focus:border-cyan-400/50 focus:ring-2 focus:ring-cyan-400/10"
          />
        </label>
        <select
          value={scope}
          onChange={(event) => setFilter(setScope, event.target.value as OrcaPresetScope | 'all')}
          className="rounded-lg border border-white/10 bg-gray-900 px-3 py-2 text-sm text-gray-200 outline-none focus:border-cyan-400/50"
        >
          <option value="all">{t('adminOrcaSchema.allScopes')}</option>
          <option value="filament">{t('adminOrcaSchema.scopes.filament')}</option>
          <option value="process">{t('adminOrcaSchema.scopes.process')}</option>
          <option value="machine">{t('adminOrcaSchema.scopes.machine')}</option>
        </select>
        <select
          value={status}
          onChange={(event) => setFilter(setStatus, event.target.value as OrcaSchemaObservationStatus | 'all')}
          className="rounded-lg border border-white/10 bg-gray-900 px-3 py-2 text-sm text-gray-200 outline-none focus:border-cyan-400/50"
        >
          <option value="all">{t('adminOrcaSchema.allStatuses')}</option>
          <option value="new">{t('adminOrcaSchema.statuses.new')}</option>
          <option value="reviewed">{t('adminOrcaSchema.statuses.reviewed')}</option>
        </select>
      </div>

      {query.isLoading ? (
        <div className="py-14 text-center text-sm text-gray-400">{t('adminOrcaSchema.loading')}</div>
      ) : query.isError ? (
        <div className="flex items-center justify-center gap-2 py-14 text-sm text-red-300">
          <CircleAlert className="h-4 w-4" />
          {t('adminOrcaSchema.loadError')}
        </div>
      ) : !data?.items.length ? (
        <div className="rounded-xl border border-dashed border-white/15 py-14 text-center">
          <Check className="mx-auto mb-3 h-8 w-8 text-emerald-400" />
          <p className="font-medium text-white">{t('adminOrcaSchema.empty')}</p>
          <p className="mt-1 text-sm text-gray-500">{t('adminOrcaSchema.emptyHint')}</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-white/10">
          {data.items.map((item) => (
            <article
              key={item.id}
              className="grid gap-3 border-b border-white/10 bg-white/[0.035] p-4 last:border-b-0 hover:bg-white/[0.055] lg:grid-cols-[minmax(220px,1.4fr)_110px_120px_90px_minmax(150px,1fr)_auto] lg:items-center"
            >
              <div className="min-w-0">
                <code className="break-all text-sm font-semibold text-cyan-200">{item.field_name}</code>
                <p className="mt-1 text-xs text-gray-500">{item.last_source}</p>
              </div>
              <span className="w-fit rounded border border-white/10 bg-black/20 px-2 py-1 text-xs text-gray-300">
                {t(`adminOrcaSchema.scopes.${item.scope}`)}
              </span>
              <code className="text-xs text-gray-300">{item.value_shape}</code>
              <span className="text-xs text-gray-400">× {item.occurrences}</span>
              <div className="text-xs text-gray-400">
                <p>{new Date(item.last_seen_at).toLocaleString(i18n.language)}</p>
                <p className="mt-1 text-gray-600">{t(`adminOrcaSchema.statuses.${item.status}`)}</p>
              </div>
              <div className="flex flex-wrap gap-2 lg:justify-end">
                <button
                  type="button"
                  onClick={() => copyObservation(item)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-400/10 px-2.5 py-1.5 text-xs font-medium text-cyan-200 transition hover:bg-cyan-400/20"
                >
                  <Copy className="h-3.5 w-3.5" />
                  {t('adminOrcaSchema.copyData')}
                </button>
                {item.status !== 'reviewed' && (
                  <button
                    type="button"
                    onClick={() => updateMutation.mutate({ id: item.id, nextStatus: 'reviewed' })}
                    disabled={updateMutation.isPending}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/15 px-2.5 py-1.5 text-xs font-medium text-emerald-300 transition hover:bg-emerald-500/25 disabled:opacity-50"
                  >
                    <Check className="h-3.5 w-3.5" />
                    {t('adminOrcaSchema.markReviewed')}
                  </button>
                )}
                {item.status !== 'new' && (
                  <button
                    type="button"
                    onClick={() => updateMutation.mutate({ id: item.id, nextStatus: 'new' })}
                    disabled={updateMutation.isPending}
                    className="rounded-lg p-1.5 text-gray-500 transition hover:bg-white/10 hover:text-white disabled:opacity-50"
                    title={t('adminOrcaSchema.reopen')}
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      {data && data.pages > 1 && (
        <div className="flex items-center justify-between text-sm text-gray-400">
          <span>{t('adminOrcaSchema.total', { count: data.total })}</span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1}
              className="rounded-lg bg-white/5 p-2 hover:bg-white/10 disabled:opacity-30"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span>{t('adminOrcaSchema.page', { page, pages: data.pages })}</span>
            <button
              type="button"
              onClick={() => setPage((current) => Math.min(data.pages, current + 1))}
              disabled={page >= data.pages}
              className="rounded-lg bg-white/5 p-2 hover:bg-white/10 disabled:opacity-30"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
