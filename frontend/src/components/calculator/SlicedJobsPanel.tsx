import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { FileX2, Loader2, RefreshCw, Trash2 } from 'lucide-react';

import { orcaSlicesAPI } from '../../api/client';
import { Printer3DIcon } from '../icons/Printer3DIcon';
import type { OrcaSliceReport } from '../../types/api';
import {
  requestSliceKeyCheck,
  subscribeToPluginSliceKeys,
  type PluginSliceHookState,
} from '../../utils/pluginBridge';

interface SlicedJobsPanelProps {
  /** Hands the chosen slice over for a full breakdown, file and all. */
  onPick: (slice: OrcaSliceReport) => void;
  pickingId?: number | null;
  /** Slices the plugin could not open when they were picked. */
  goneSourceKeys?: string[];
}

export const SlicedJobsPanel: React.FC<SlicedJobsPanelProps> = ({
  onPick,
  pickingId = null,
  goneSourceKeys = [],
}) => {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  // null until the plugin answers: until then every slice is offered, because
  // silence is not proof a file is missing.
  const [aliveKeys, setAliveKeys] = useState<string[] | null>(null);
  const [hook, setHook] = useState<PluginSliceHookState | null>(null);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);

  const { data: slices = [], isLoading, isError, refetch, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ['orca-slices'],
    queryFn: () => orcaSlicesAPI.list(12),
    retry: false,
  });

  const removeMutation = useMutation({
    mutationFn: (sliceId: number) => orcaSlicesAPI.remove(sliceId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['orca-slices'] }),
  });

  useEffect(
    () =>
      subscribeToPluginSliceKeys((status) => {
        setAliveKeys(status.keys);
        setHook(status.hook);
      }),
    [],
  );

  // Asked on every settled load, not on a changed list: pressing refresh is how
  // a person re-checks after putting a file back.
  useEffect(() => {
    const keys = slices.map((slice) => slice.source_key).filter((key): key is string => !!key);
    requestSliceKeyCheck(keys);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataUpdatedAt]);

  const isGone = (slice: OrcaSliceReport): boolean => {
    if (!slice.source_key) {
      return true;
    }
    if (goneSourceKeys.includes(slice.source_key)) {
      return true;
    }
    return aliveKeys !== null && !aliveKeys.includes(slice.source_key);
  };

  const handleRemove = (sliceId: number) => {
    if (confirmingId !== sliceId) {
      setConfirmingId(sliceId);
      return;
    }
    setConfirmingId(null);
    removeMutation.mutate(sliceId);
  };

  return (
    <div className="rounded-[1.5rem] border border-white/10 bg-white/5 p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-white">{t('slicedJobs.title')}</p>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          title={t('slicedJobs.refresh')}
          className="rounded p-1 text-slate-400 transition hover:bg-white/10 hover:text-white disabled:opacity-40"
        >
          {isFetching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* Where this is switched on comes first, always: a list without it leaves
          a person guessing what produced it and how to get more. */}
      <p className="mb-3 text-[11px] leading-4 text-slate-400">
        {hook
          ? t(hook.enabled ? 'slicedJobs.hookOn' : 'slicedJobs.hookOff', { preset: hook.preset })
          : t('slicedJobs.howToEnable')}
      </p>

      {isLoading ? (
        <div className="flex justify-center py-6">
          <Loader2 className="h-5 w-5 animate-spin text-cyan-300" />
        </div>
      ) : slices.length === 0 ? (
        <div className="py-3">
          <p className="text-center text-xs text-slate-500">
            {hook?.enabled ? t('slicedJobs.emptyEnabled') : t('slicedJobs.empty')}
          </p>
          {isError && (
            <p className="mt-2 text-center text-[11px] text-slate-500">{t('slicedJobs.loadError')}</p>
          )}
        </div>
      ) : (
        <div className="max-h-[13rem] space-y-1.5 overflow-y-auto">
          {slices.map((slice) => {
            const gone = isGone(slice);
            return (
              <div
                key={slice.id}
                className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl px-3 py-2 ${
                  gone ? 'bg-white/[0.03]' : 'bg-white/5'
                }`}
              >
                <p
                  className={`min-w-0 flex-1 truncate text-xs font-medium ${
                    gone ? 'text-slate-500' : 'text-white'
                  }`}
                  title={slice.file_name}
                >
                  {slice.file_name}
                </p>
                {!gone && (
                  <button
                    type="button"
                    onClick={() => onPick(slice)}
                    disabled={pickingId === slice.id}
                    className="shrink-0 rounded-lg bg-cyan-500/15 px-2.5 py-1 text-[11px] font-medium text-cyan-200 transition hover:bg-cyan-500/25 disabled:opacity-50"
                  >
                    {pickingId === slice.id ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      t('slicedJobs.use')
                    )}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => handleRemove(slice.id)}
                  onBlur={() => setConfirmingId((current) => (current === slice.id ? null : current))}
                  disabled={removeMutation.isPending && removeMutation.variables === slice.id}
                  title={t('slicedJobs.remove')}
                  className={`shrink-0 rounded-lg px-2 py-1 text-[11px] transition ${
                    confirmingId === slice.id
                      ? 'bg-rose-500/20 text-rose-200'
                      : 'text-slate-500 hover:bg-white/10 hover:text-slate-300'
                  }`}
                >
                  {confirmingId === slice.id ? t('slicedJobs.confirmRemove') : <Trash2 className="h-3 w-3" />}
                </button>
                <p className="flex w-full items-center gap-1.5 text-[11px] text-slate-400">
                  <Printer3DIcon className="shrink-0" size={12} strokeWidth={2} />
                  <span className="truncate">
                    {slice.physical_printer_name ?? slice.printer_model ?? t('slicedJobs.unknownPrinter')}
                  </span>
                  <span className="ml-auto shrink-0 text-slate-500">
                    {new Date(slice.sliced_at ?? slice.received_at).toLocaleString(i18n.language, {
                      day: '2-digit',
                      month: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                </p>
                {gone && (
                  <p className="flex w-full items-center gap-1.5 text-[11px] text-slate-500">
                    <FileX2 className="h-3 w-3 shrink-0" />
                    <span>{t('slicedJobs.fileGone')}</span>
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
