import { useState } from 'react';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Laptop, Loader2, RefreshCw, ShieldCheck, Smartphone, Tablet, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  authAPI,
  type AccountSession,
  type AccountSessionDeviceType,
} from '../api/client';

const PAGE_SIZE = 10;

export const activeSessionsQueryKey = (userId: number) => ['account-sessions', userId] as const;

const deviceIcon = (deviceType: AccountSessionDeviceType) => {
  if (deviceType === 'mobile') return Smartphone;
  if (deviceType === 'tablet') return Tablet;
  return Laptop;
};

export const ActiveSessions: React.FC<{ userId: number }> = ({ userId }) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState(false);
  const queryKey = activeSessionsQueryKey(userId);
  const sessionsQuery = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam, signal }) => authAPI.listSessions({ page: pageParam, size: PAGE_SIZE }, signal),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => lastPage.page < lastPage.pages ? lastPage.page + 1 : undefined,
    staleTime: 30_000,
  });

  const refresh = () => {
    setActionError(false);
    void sessionsQuery.refetch();
  };
  const finishMutation = async () => {
    setActionError(false);
    await queryClient.invalidateQueries({ queryKey });
  };
  const revokeSession = useMutation({
    mutationFn: authAPI.revokeSession,
    onSuccess: finishMutation,
    onError: () => setActionError(true),
  });
  const revokeOthers = useMutation({
    mutationFn: authAPI.revokeOtherSessions,
    onSuccess: finishMutation,
    onError: () => setActionError(true),
  });

  const sessions = sessionsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const total = sessionsQuery.data?.pages[0]?.total ?? 0;
  const otherCount = Math.max(0, total - (sessions.some((session) => session.is_current) ? 1 : 0));

  const activityLabel = (session: AccountSession) => {
    if (session.is_current) return t('settings.activeSessions.activityNow');
    const ageMinutes = Math.max(0, Math.floor((Date.now() - Date.parse(session.last_seen_at)) / 60_000));
    if (ageMinutes < 5) return t('settings.activeSessions.activityRecently');
    if (ageMinutes < 60) return t('settings.activeSessions.activityMinutes', { count: ageMinutes });
    if (ageMinutes < 24 * 60) {
      return t('settings.activeSessions.activityHours', { count: Math.floor(ageMinutes / 60) });
    }
    if (ageMinutes < 7 * 24 * 60) {
      return t('settings.activeSessions.activityDays', { count: Math.floor(ageMinutes / (24 * 60)) });
    }
    return t('settings.activeSessions.activityEarlier');
  };

  return (
    <section className="rounded-2xl border border-white/10 bg-slate-950/55 p-5 shadow-2xl shadow-black/20 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="rounded-lg bg-emerald-500/15 p-2">
            <ShieldCheck className="h-5 w-5 text-emerald-300" />
          </div>
          <div className="min-w-0">
            <h3 className="text-lg font-bold text-white">{t('settings.activeSessions.title')}</h3>
            <p className="mt-0.5 text-xs leading-5 text-gray-400">
              {t('settings.activeSessions.description')}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={sessionsQuery.isFetching}
          className="inline-flex min-h-9 shrink-0 items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-gray-200 transition hover:bg-white/10 disabled:cursor-wait disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${sessionsQuery.isFetching ? 'animate-spin' : ''}`} />
          {t('settings.activeSessions.refresh')}
        </button>
      </div>

      {sessionsQuery.isPending ? (
        <div className="mt-5 flex items-center gap-2 text-sm text-gray-400" role="status">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t('settings.activeSessions.loading')}
        </div>
      ) : sessionsQuery.isError && sessions.length === 0 ? (
        <div className="mt-5 rounded-xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
          <p>{t('settings.activeSessions.loadError')}</p>
          <button type="button" onClick={refresh} className="mt-3 inline-flex rounded-lg border border-red-300/30 px-3 py-2 text-xs font-semibold hover:bg-red-400/10">
            {t('settings.activeSessions.tryAgain')}
          </button>
        </div>
      ) : (
        <>
          {(sessionsQuery.isRefetchError || actionError) && (
            <p className="mt-4 rounded-xl border border-amber-300/20 bg-amber-400/10 px-3 py-2 text-xs text-amber-100" role="alert">
              {t(actionError ? 'settings.activeSessions.actionError' : 'settings.activeSessions.refreshError')}
            </p>
          )}
          <div className="mt-5 divide-y divide-white/10 overflow-hidden rounded-xl border border-white/10 bg-white/[0.035]">
            {sessions.map((session) => {
              const DeviceIcon = deviceIcon(session.device_type);
              const label = [
                t(`settings.activeSessions.browser.${session.browser}`),
                t(`settings.activeSessions.os.${session.os}`),
                t(`settings.activeSessions.device.${session.device_type}`),
              ].join(' · ');
              return (
                <div key={session.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                  <div className="flex min-w-0 items-center gap-3">
                    <DeviceIcon className="h-5 w-5 shrink-0 text-gray-400" />
                    <div className="min-w-0">
                      <p className="break-words text-sm font-medium text-white">{label}</p>
                      <p className={`mt-1 text-xs ${session.is_current ? 'text-emerald-300' : 'text-gray-400'}`}>
                        {activityLabel(session)}
                        {session.is_current ? ` · ${t('settings.activeSessions.current')}` : ''}
                      </p>
                    </div>
                  </div>
                  {!session.is_current && (
                    <button
                      type="button"
                      onClick={() => revokeSession.mutate(session.id)}
                      disabled={revokeSession.isPending || revokeOthers.isPending}
                      aria-label={t('settings.activeSessions.revokeNamed', { device: label })}
                      className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-lg border border-red-300/20 px-3 py-2 text-xs font-medium text-red-200 transition hover:bg-red-400/10 disabled:cursor-wait disabled:opacity-50"
                    >
                      {revokeSession.isPending && revokeSession.variables === session.id
                        ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        : <X className="h-3.5 w-3.5" />}
                      {t('settings.activeSessions.revoke')}
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            {sessionsQuery.hasNextPage && (
              <button
                type="button"
                onClick={() => void sessionsQuery.fetchNextPage()}
                disabled={sessionsQuery.isFetchingNextPage}
                className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-gray-200 transition hover:bg-white/10 disabled:cursor-wait disabled:opacity-50"
              >
                {sessionsQuery.isFetchingNextPage && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                {t('settings.activeSessions.loadMore')}
              </button>
            )}
            {otherCount > 0 && (
              <button
                type="button"
                onClick={() => revokeOthers.mutate()}
                disabled={revokeOthers.isPending || revokeSession.isPending}
                className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-red-300/20 px-3 py-2 text-xs font-medium text-red-200 transition hover:bg-red-400/10 disabled:cursor-wait disabled:opacity-50"
              >
                {revokeOthers.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                {t('settings.activeSessions.revokeOthers')}
              </button>
            )}
          </div>
        </>
      )}

      <p className="mt-4 text-xs leading-5 text-gray-500">
        {t('settings.activeSessions.connectedAppsSeparate')}
      </p>
    </section>
  );
};
