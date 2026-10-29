import { useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Bell, ChevronDown, Loader2 } from 'lucide-react';

import { spoolsAPI, type SpoolGroup, type SpoolGroupsParams, type UserSpool } from '../api/client';
import type { ViewMode } from './ViewModeToggle';
import { SpoolIcon } from './icons/SpoolIcon';
import { formatNetWeight } from '../utils/packaging';
import { mergeSpoolFeedPages, spoolQueryKeys } from '../utils/spoolQueries';

type GroupFilters = Omit<SpoolGroupsParams, 'cursor' | 'limit' | 'group_by'>;

export type SpoolGrouping = NonNullable<SpoolGroupsParams['group_by']>;

interface SpoolGroupListProps {
  userId: number | null | undefined;
  filters: GroupFilters;
  /** How the shelf is folded; the default is one group per product. */
  groupBy?: SpoolGrouping;
  viewMode: ViewMode;
  renderSpool: (spool: UserSpool) => ReactNode;
  /** Material alert state for f:/c: groups; lone s: groups have no material rule. */
  materialAlertOn?: (key: string) => boolean;
  onOpenMaterialAlert?: (group: SpoolGroup, name: string) => void;
}

export const isMaterialGroupKey = (key: string) => /^[fc]:\d+$/.test(key);

/** Spools with no catalog card (or no manufacturer/type to fold by): always a group of their own. */
export const isUncardedGroupKey = (key: string) => key === 'n:0' || key === 'b:0' || key === 't:_none';

const isFoldKey = (key: string) => /^[bt]:/.test(key);

export const spoolGroupName = (spool: UserSpool, fallback: string) => (
  spool.filament?.name || spool.extra?.display_name || fallback
);

const PAGE_SIZE = 24;

const spoolLayoutClass = (viewMode: ViewMode) => (
  viewMode === 'grid' ? 'grid grid-cols-1 gap-4 md:grid-cols-2' : 'space-y-2'
);

function LoadMoreButton({ loading, failed, onClick }: { loading: boolean; failed: boolean; onClick: () => void }) {
  const { t } = useTranslation();
  return (
    <div>
      <button
        type="button"
        onClick={onClick}
        disabled={loading}
        className="inline-flex items-center gap-2 rounded-lg border border-white/15 px-3 py-2 text-sm text-gray-200 transition hover:bg-white/10 disabled:opacity-60"
      >
        {loading && <Loader2 className="h-4 w-4 animate-spin" />}
        {loading ? t('profilePage.spoolsLoadingMore') : t('profilePage.spoolsLoadMore')}
      </button>
      {failed && <p className="mt-2 text-xs text-amber-200">{t('profilePage.spoolsLoadMoreError')}</p>}
    </div>
  );
}

function GroupSpools({ userId, filters, group, viewMode, renderSpool }: SpoolGroupListProps & { group: SpoolGroup }) {
  const { t } = useTranslation();
  const params = useMemo(() => ({ ...filters, group_key: group.key, limit: PAGE_SIZE }), [filters, group.key]);
  const query = useInfiniteQuery({
    queryKey: spoolQueryKeys.feed(userId, params),
    queryFn: ({ pageParam, signal }) => spoolsAPI.feed({ ...params, cursor: pageParam }, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: !!userId,
    staleTime: 60_000,
  });
  const spools = useMemo(() => mergeSpoolFeedPages(query.data?.pages), [query.data?.pages]);

  if (query.isPending) {
    return (
      <p className="flex items-center gap-2 px-1 py-2 text-sm text-gray-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('profilePage.spoolsLoading')}
      </p>
    );
  }
  if (query.isError && !query.isFetchNextPageError) {
    return (
      <div className="flex flex-wrap items-center gap-3 px-1 py-2 text-sm text-red-200">
        <span>{t('profilePage.spoolsLoadError')}</span>
        <button type="button" onClick={() => query.refetch()} className="rounded-lg border border-red-300/30 px-3 py-1">
          {t('profilePage.spoolsRetry')}
        </button>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className={spoolLayoutClass(viewMode)}>
        {spools.map((spool) => <div key={spool.id} className="min-w-0">{renderSpool(spool)}</div>)}
      </div>
      {query.hasNextPage && (
        <LoadMoreButton
          loading={query.isFetchingNextPage}
          failed={query.isFetchNextPageError}
          onClick={() => void query.fetchNextPage()}
        />
      )}
    </div>
  );
}

interface GroupHeaderProps {
  group: SpoolGroup;
  expanded: boolean;
  onToggle: () => void;
  panelId: string;
  alertOn?: boolean;
  onOpenAlert?: (name: string) => void;
}

function GroupHeader({ group, expanded, onToggle, panelId, alertOn, onOpenAlert }: GroupHeaderProps) {
  const { t, i18n } = useTranslation();
  const spool = group.latest_spool;
  const color = group.key.startsWith('f:') || group.key.startsWith('c:')
    ? (spool.filament?.color_hex
      ? `#${spool.filament.color_hex.replace('#', '')}`
      : spool.extra?.color_hex || '#9333ea')
    : '#9333ea';
  const uncarded = isUncardedGroupKey(group.key);
  const folded = isFoldKey(group.key);
  let name = spoolGroupName(spool, t('profilePage.spoolNoFilament'));
  if (uncarded) name = t('profilePage.spoolShelf.noCatalogCard');
  else if (group.key.startsWith('b:')) name = spool.filament?.brand_name || name;
  else if (group.key.startsWith('t:')) name = group.key.slice(2);
  const details = spool.filament
    ? [spool.filament.brand_name, spool.filament.material_type]
    : [spool.extra?.vendor, spool.extra?.material];
  const detailText = folded || uncarded ? '' : details.filter(Boolean).join(' · ');
  const availableCount = group.state_counts.active + group.state_counts.shelf;
  const showGrams = availableCount > 0
    && (group.available_remaining_weight_g > 0 || group.unknown_mass_count === 0);

  return (
    <div className="flex items-stretch">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={panelId}
        className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5 text-left transition-colors hover:bg-white/5 sm:flex-nowrap"
      >
        <ChevronDown
          className={`h-4 w-4 flex-shrink-0 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
          aria-hidden
        />
        <SpoolIcon pct={100} color={color} size={36} viewBox="8 12 78 72" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-white">{name}</p>
          {detailText && <p className="truncate text-xs text-gray-400">{detailText}</p>}
        </div>
        <div className="flex w-full flex-wrap items-center gap-x-3 gap-y-0.5 pl-[4.75rem] text-xs sm:ml-auto sm:w-auto sm:flex-shrink-0 sm:justify-end sm:pl-0">
          <span className="rounded-full border border-white/15 bg-white/5 px-2 py-0.5 text-gray-200">
            {t('profilePage.spoolShelf.spoolCount', { count: group.spool_count })}
          </span>
          {showGrams && (
            <span className="font-medium text-green-300">
              {t('profilePage.spoolShelf.gramsLeft', {
                weight: formatNetWeight(group.available_remaining_weight_g, t, i18n?.language ?? 'en'),
              })}
            </span>
          )}
          {group.unknown_mass_count > 0 && (
            <span className="text-gray-500">
              {t('profilePage.spoolShelf.unknownMass', { count: group.unknown_mass_count })}
            </span>
          )}
        </div>
      </button>
      {onOpenAlert && (
        <button
          type="button"
          onClick={() => onOpenAlert(name)}
          title={t('profilePage.stockAlerts.materialButton')}
          aria-label={t('profilePage.stockAlerts.materialButton')}
          aria-pressed={!!alertOn}
          className={`flex-shrink-0 border-l border-white/10 px-3 transition-colors hover:bg-white/5 ${
            alertOn ? 'text-purple-300' : 'text-gray-500 hover:text-gray-200'
          }`}
        >
          <Bell className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

export function SpoolGroupList(props: SpoolGroupListProps) {
  const { userId, filters, groupBy = 'product', viewMode, renderSpool, materialAlertOn, onOpenMaterialAlert } = props;
  const { t } = useTranslation();
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(() => new Set());
  const params = useMemo(() => ({ ...filters, group_by: groupBy, limit: PAGE_SIZE }), [filters, groupBy]);

  const query = useInfiniteQuery({
    queryKey: spoolQueryKeys.groups(userId, params),
    queryFn: ({ pageParam, signal }) => spoolsAPI.groups({ ...params, cursor: pageParam }, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: !!userId,
    staleTime: 60_000,
  });

  const groups = useMemo(() => {
    const byKey = new Map<string, SpoolGroup>();
    for (const page of query.data?.pages ?? []) {
      for (const group of page.items) byKey.set(group.key, group);
    }
    return [...byKey.values()];
  }, [query.data?.pages]);

  // Single-spool groups render as plain cards; consecutive ones share a grid
  // so the grid view keeps its columns without holes between group shells.
  const runs = useMemo(() => {
    const result: Array<{ single: boolean; items: SpoolGroup[] }> = [];
    for (const group of groups) {
      const single = group.spool_count === 1 && !isUncardedGroupKey(group.key);
      const last = result[result.length - 1];
      if (last && last.single && single) last.items.push(group);
      else result.push({ single, items: [group] });
    }
    return result;
  }, [groups]);

  const toggle = (key: string) => {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  if (query.isPending) {
    return (
      <p className="flex items-center gap-2 text-sm text-gray-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('profilePage.spoolsLoading')}
      </p>
    );
  }
  if (query.isError && !query.isFetchNextPageError) {
    return (
      <div className="rounded-xl border border-red-400/25 bg-red-500/10 px-4 py-3 text-sm text-red-100">
        <p>{t('profilePage.spoolsLoadError')}</p>
        <button type="button" onClick={() => query.refetch()} className="mt-2 inline-flex rounded-lg border border-red-300/30 px-3 py-2">
          {t('profilePage.spoolsRetry')}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className={viewMode === 'grid' ? 'space-y-4' : 'space-y-2'}>
        {runs.map((run) => (run.single ? (
          <div key={`single-${run.items[0].key}`} className={spoolLayoutClass(viewMode)}>
            {run.items.map((group) => (
              <div key={group.key} className="min-w-0">{renderSpool(group.latest_spool)}</div>
            ))}
          </div>
        ) : (
          (() => {
            const group = run.items[0];
            const expanded = expandedKeys.has(group.key);
            const panelId = `spool-group-${group.key.replace(':', '-')}`;
            return (
              <section
                key={group.key}
                className={`glass-panel overflow-hidden rounded-xl border shadow-lg ${expanded ? 'border-purple-400/40' : 'border-white/15'}`}
              >
                <GroupHeader
                  group={group}
                  expanded={expanded}
                  onToggle={() => toggle(group.key)}
                  panelId={panelId}
                  alertOn={materialAlertOn?.(group.key)}
                  onOpenAlert={onOpenMaterialAlert && isMaterialGroupKey(group.key)
                    ? (name) => onOpenMaterialAlert(group, name)
                    : undefined}
                />
                {expanded && (
                  <div id={panelId} className="border-t border-white/10 bg-black/10 p-2 md:p-3">
                    <GroupSpools {...props} group={group} />
                  </div>
                )}
              </section>
            );
          })()
        )))}
      </div>
      {query.hasNextPage && (
        <LoadMoreButton
          loading={query.isFetchingNextPage}
          failed={query.isFetchNextPageError}
          onClick={() => void query.fetchNextPage()}
        />
      )}
    </div>
  );
}
