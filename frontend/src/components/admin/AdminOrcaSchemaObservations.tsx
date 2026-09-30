import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Copy,
  RefreshCw,
  ScanSearch,
  Search,
} from 'lucide-react';

import { adminAPI } from '../../api/client';
import { ModalOverlay } from '../ModalOverlay';
import { toast } from '../Toast';
import type {
  OrcaPresetScope,
  OrcaSchemaObservationStatus,
  OrcaSchemaObservationListResponse,
} from '../../types/api';

const PAGE_SIZE = 25;
const COPY_PAGE_SIZE = 100;
const MAX_COPY_PAGES = 100;

type Observation = OrcaSchemaObservationListResponse['items'][number];

function metadata(item: Observation) {
  return {
    field_name: item.field_name,
    scope: item.scope,
    value_shape: item.value_shape,
    status: item.status,
    occurrences: item.occurrences,
    first_source: item.first_source,
    last_source: item.last_source,
    first_seen_at: item.first_seen_at,
    last_seen_at: item.last_seen_at,
    registry_version: item.registry_version,
  };
}

export function AdminOrcaSchemaObservations() {
  const { t, i18n } = useTranslation();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<OrcaSchemaObservationStatus | 'all'>('new');
  const [scope, setScope] = useState<OrcaPresetScope | 'all'>('all');
  const [search, setSearch] = useState('');
  const [copying, setCopying] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);
  const [manualText, setManualText] = useState<string | null>(null);
  const copyRun = useRef(0);

  useEffect(() => () => { copyRun.current += 1; }, []);

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

  const data = query.data;
  const registryDigest = data?.registry_version.split(':').at(-1)?.slice(0, 12) ?? '—';
  const setFilter = <T,>(setter: (value: T) => void, value: T) => {
    copyRun.current += 1;
    setCopying(false);
    setCopyError(null);
    setManualText(null);
    setter(value);
    setPage(1);
  };

  const copyList = async () => {
    if (copying || query.isFetching || query.isError || !data?.total) return;
    const run = ++copyRun.current;
    const current = () => run === copyRun.current;
    const filters = { status, scope, search: search.trim() };
    const requestFilters = {
      status: status === 'all' ? undefined : status,
      scope: scope === 'all' ? undefined : scope,
      search: filters.search || undefined,
    };
    setCopying(true);
    setCopyError(null);
    setManualText(null);
    try {
      const items: Observation[] = [];
      const seen = new Set<number>();
      let expectedTotal = 0;
      let expectedPages = 0;
      let registryVersion = '';

      for (let nextPage = 1; nextPage <= MAX_COPY_PAGES; nextPage += 1) {
        const response = await adminAPI.listOrcaSchemaObservations({
          ...requestFilters,
          page: nextPage,
          size: COPY_PAGE_SIZE,
        });
        if (!current()) return;
        if (nextPage === 1) {
          expectedTotal = response.total;
          expectedPages = Math.ceil(expectedTotal / COPY_PAGE_SIZE);
          registryVersion = response.registry_version;
          if (!Number.isSafeInteger(expectedTotal) || expectedTotal < 1
            || expectedPages > MAX_COPY_PAGES) throw new Error('inconsistent');
        }
        const expectedLength = Math.min(COPY_PAGE_SIZE, expectedTotal - items.length);
        if (response.page !== nextPage || response.size !== COPY_PAGE_SIZE
          || response.total !== expectedTotal || response.pages !== expectedPages
          || response.registry_version !== registryVersion
          || response.items.length !== expectedLength) throw new Error('inconsistent');
        for (const item of response.items) {
          if (seen.has(item.id)) throw new Error('inconsistent');
          seen.add(item.id);
          items.push(item);
        }
        if (nextPage === expectedPages) break;
      }
      if (items.length !== expectedTotal || !current()) throw new Error('inconsistent');
      const text = JSON.stringify({
        filters,
        bundle_registry_version: registryVersion,
        count: items.length,
        observations: items.map(metadata),
      }, null, 2);
      try {
        if (!navigator.clipboard?.writeText) throw new Error('clipboard-unavailable');
        await navigator.clipboard.writeText(text);
        if (current()) toast.success(t('adminOrcaSchema.listCopied'));
      } catch {
        if (current()) setManualText(text);
      }
    } catch (error) {
      if (current()) setCopyError(t(error instanceof Error && error.message === 'inconsistent'
        ? 'adminOrcaSchema.copyListChanged' : 'adminOrcaSchema.copyListLoadError'));
    } finally {
      if (current()) setCopying(false);
    }
  };

  return (
    <div className="min-w-0 space-y-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="shrink-0 rounded-xl border border-cyan-400/20 bg-cyan-400/10 p-2.5">
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
          </div>
        </div>
        <div className="shrink-0 self-start">
          <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400">
            <span>{t('adminOrcaSchema.registry')}</span>
            <code className="text-cyan-300">{registryDigest}</code>
            <button
              type="button"
              onClick={() => query.refetch()}
              className="rounded p-1 text-gray-400 transition-colors hover:bg-white/10 hover:text-white"
              aria-label={t('adminOrcaSchema.refresh')}
              title={t('adminOrcaSchema.refresh')}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${query.isFetching ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </div>

      {copyError && <p role="alert" className="text-sm text-red-300">{copyError}</p>}

      <div className="grid gap-3 rounded-xl border border-white/10 bg-black/10 p-3 md:grid-cols-[minmax(0,1fr)_auto_auto]">
        <label className="relative block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
          <input
            value={search}
            onChange={(event) => setFilter(setSearch, event.target.value)}
            aria-label={t('adminOrcaSchema.search')}
            placeholder={t('adminOrcaSchema.search')}
            className="w-full rounded-lg border border-white/10 bg-white/5 py-2 pl-9 pr-3 text-sm text-white outline-none transition focus:border-cyan-400/50 focus:ring-2 focus:ring-cyan-400/10"
          />
        </label>
        <select
          value={scope}
          onChange={(event) => setFilter(setScope, event.target.value as OrcaPresetScope | 'all')}
          aria-label={t('adminOrcaSchema.scopeFilter')}
          className="max-w-full rounded-lg border border-white/10 bg-gray-900 px-3 py-2 text-sm text-gray-200 outline-none focus:border-cyan-400/50"
        >
          <option value="all">{t('adminOrcaSchema.allScopes')}</option>
          <option value="filament">{t('adminOrcaSchema.scopes.filament')}</option>
          <option value="process">{t('adminOrcaSchema.scopes.process')}</option>
          <option value="machine">{t('adminOrcaSchema.scopes.machine')}</option>
        </select>
        <select
          value={status}
          onChange={(event) => setFilter(setStatus, event.target.value as OrcaSchemaObservationStatus | 'all')}
          aria-label={t('adminOrcaSchema.statusFilter')}
          className="max-w-full rounded-lg border border-white/10 bg-gray-900 px-3 py-2 text-sm text-gray-200 outline-none focus:border-cyan-400/50"
        >
          <option value="all">{t('adminOrcaSchema.allStatuses')}</option>
          <option value="new">{t('adminOrcaSchema.statuses.new')}</option>
          <option value="reviewed">{t('adminOrcaSchema.statuses.reviewed')}</option>
        </select>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          {data && <p className="text-sm font-medium text-gray-200">{t('adminOrcaSchema.total', { count: data.total })}</p>}
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-gray-400">{t('adminOrcaSchema.copyListHint')}</p>
        </div>
        <button
          type="button"
          onClick={copyList}
          disabled={copying || query.isFetching || query.isError || !data?.total}
          className="inline-flex shrink-0 items-center justify-center gap-2 self-start rounded-lg border border-cyan-400/25 bg-cyan-400/15 px-4 py-2.5 text-sm font-medium text-cyan-100 transition hover:bg-cyan-400/25 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Copy className="h-4 w-4" />
          {t(copying ? 'adminOrcaSchema.copyingList' : 'adminOrcaSchema.copyList')}
        </button>
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
          <div aria-hidden="true" className="hidden grid-cols-[minmax(0,1fr)_8rem_7rem_6rem_12rem] items-center gap-4 border-b border-white/10 bg-black/20 px-4 py-3 text-xs font-medium text-gray-400 lg:grid">
            <span>{t('adminOrcaSchema.fieldName')}</span>
            <span>{t('adminOrcaSchema.scopeFilter')}</span>
            <span>{t('adminOrcaSchema.valueShape')}</span>
            <span className="text-right">{t('adminOrcaSchema.occurrences')}</span>
            <span>{t('adminOrcaSchema.lastSeen')}</span>
          </div>
          {data.items.map((item) => (
            <article
              key={item.id}
              className="grid grid-cols-[auto_1fr_auto] items-center gap-x-4 gap-y-2 border-b border-white/10 bg-white/[0.035] px-4 py-3.5 last:border-b-0 hover:bg-white/[0.055] lg:grid-cols-[minmax(0,1fr)_8rem_7rem_6rem_12rem]"
            >
              <div className="col-span-3 min-w-0 lg:col-span-1">
                <code className="break-all text-sm font-semibold text-cyan-200">{item.field_name}</code>
                <p className="mt-1 text-xs text-gray-500">{item.last_source}</p>
              </div>
              <span className="w-fit rounded border border-white/10 bg-black/20 px-2 py-1 text-xs text-gray-300">
                {t(`adminOrcaSchema.scopes.${item.scope}`)}
              </span>
              <code className="text-xs text-gray-300">{item.value_shape}</code>
              <span title={t('adminOrcaSchema.occurrences')} className="text-right text-xs tabular-nums text-gray-300">× {item.occurrences}</span>
              <div className="col-span-3 text-xs tabular-nums text-gray-400 lg:col-span-1">
                <p>{new Date(item.last_seen_at).toLocaleString(i18n.language)}</p>
                {item.status === 'reviewed' && <p className="mt-1 text-gray-400">{t('adminOrcaSchema.statuses.reviewed')}</p>}
              </div>
            </article>
          ))}
        </div>
      )}

      <p className="max-w-4xl text-xs leading-relaxed text-gray-400">{t('adminOrcaSchema.queueHint')}</p>

      {data && data.pages > 1 && (
        <div className="flex items-center justify-between text-sm text-gray-400">
          <span>{t('adminOrcaSchema.total', { count: data.total })}</span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1}
              aria-label={t('adminOrcaSchema.previousPage')}
              className="rounded-lg bg-white/5 p-2 hover:bg-white/10 disabled:opacity-30"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span>{t('adminOrcaSchema.page', { page, pages: data.pages })}</span>
            <button
              type="button"
              onClick={() => setPage((current) => Math.min(data.pages, current + 1))}
              disabled={page >= data.pages}
              aria-label={t('adminOrcaSchema.nextPage')}
              className="rounded-lg bg-white/5 p-2 hover:bg-white/10 disabled:opacity-30"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {manualText !== null && (
        <ModalOverlay onClose={() => setManualText(null)}>
          <div role="dialog" aria-modal="true" aria-labelledby="orca-copy-list-title" className="max-h-[calc(100dvh-2rem)] w-full max-w-3xl overflow-y-auto rounded-xl border border-white/15 bg-gray-900 p-5 text-white">
            <h3 id="orca-copy-list-title" className="text-lg font-semibold">{t('adminOrcaSchema.manualCopyTitle')}</h3>
            <p className="mt-2 text-sm text-gray-300">{t('adminOrcaSchema.manualCopyHint')}</p>
            <textarea
              readOnly
              aria-label={t('adminOrcaSchema.manualCopyTitle')}
              value={manualText}
              onFocus={(event) => event.currentTarget.select()}
              className="mt-4 h-64 w-full resize-y rounded-lg border border-white/15 bg-black/30 p-3 font-mono text-xs text-gray-100"
            />
            <div className="mt-4 flex justify-end">
              <button type="button" onClick={() => setManualText(null)} className="rounded-lg bg-white/10 px-4 py-2 text-sm hover:bg-white/20">
                {t('adminOrcaSchema.close')}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}
