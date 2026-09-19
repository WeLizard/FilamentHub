import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { AlertTriangle, Loader2, Undo2, X } from 'lucide-react';

import { spoolsAPI } from '../api/client';
import type { UserSpool } from '../api/client';
import type { SpoolUsageEvent } from '../types/api';
import { ModalOverlay } from './ModalOverlay';
import { toast } from './Toast';
import { translateApiError } from '../utils/translateApiError';

interface SpoolUsageModalProps {
  spool: UserSpool;
  isOpen: boolean;
  onClose: () => void;
}

/** A measurement states what was actually on the spool; reverting it would fake
 *  the reading instead of correcting a mistake. */
const MEASUREMENT = 'reconcile_adjust';

const ESTIMATE_SOURCE_KEYS: Record<string, string> = {
  slicer_gcode: 'spoolUsage.source.estimateSlicerGcode',
  slicer_3mf: 'spoolUsage.source.estimateSlicer3mf',
  slicer_progress: 'spoolUsage.source.estimateSlicerProgress',
  ams_remaining: 'spoolUsage.source.estimateAmsRemaining',
};

const formatWeight = (weight: number, locale: string, precise = false) =>
  new Intl.NumberFormat(locale, {
    maximumFractionDigits: precise ? (Math.abs(weight) < 1 ? 2 : 1) : 0,
  }).format(Math.abs(weight));

function warningFor(event: SpoolUsageEvent, t: TFunction): string | null {
  const meta = event.meta ?? {};
  if (meta.balance_accounting === 'already_in_balance') {
    return t('spoolUsage.alreadyInBalance', { reported: meta.reported_weight_g });
  }
  if (meta.balance_accounting === 'reconciled_by_measurement') {
    return t('spoolUsage.reconciledByMeasurement', { reported: meta.reported_weight_g });
  }
  if (meta.balance_accounting === 'needs_reconciliation') {
    return t('spoolUsage.needsReconciliation', { reported: meta.reported_weight_g });
  }
  if (meta.possible_repeat) {
    return t('spoolUsage.warnRepeat');
  }
  if (
    typeof meta.reported_weight_g === 'number'
    && typeof event.delta_weight_g === 'number'
    && meta.reported_weight_g - event.delta_weight_g > 0.01
  ) {
    return t(
      meta.consumption_kind === 'estimated'
        ? 'spoolUsage.warnEstimatedShortfall'
        : 'spoolUsage.warnReported',
      { reported: meta.reported_weight_g.toFixed(1) },
    );
  }
  return null;
}

export const SpoolUsageModal: React.FC<SpoolUsageModalProps> = ({ spool, isOpen, onClose }) => {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState<number | null>(null);

  const { data: events = [], isLoading } = useQuery({
    queryKey: ['spool-usage', spool.id],
    queryFn: () => spoolsAPI.usage(spool.id),
    enabled: isOpen,
  });

  const revert = useMutation({
    mutationFn: (eventId: number) => spoolsAPI.revertUsage(spool.id, eventId),
    onSuccess: () => {
      setConfirming(null);
      queryClient.invalidateQueries({ queryKey: ['spool-usage', spool.id] });
      queryClient.invalidateQueries({ queryKey: ['spools'] });
      queryClient.invalidateQueries({ queryKey: ['user-spools'] });
    },
    onError: (error: any) => {
      toast.error(translateApiError(t, error?.response?.data?.detail, t('common.error')));
    },
  });

  if (!isOpen) return null;

  const measurement = events.find(
    (event) => event.event_type === MEASUREMENT && event.meta?.reason !== 'opening_balance',
  );
  const drift = measurement?.delta_weight_g ?? 0;

  return (
    <ModalOverlay onClose={onClose}>
      <div className="w-full max-w-xl rounded-2xl border border-white/20 bg-gray-900 p-5 shadow-xl">
        <div className="mb-1 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate text-base font-semibold text-white">
              {t('spoolUsage.title', {
                name: spool.filament?.name ?? t('profilePage.spoolNoFilament'),
              })}
            </h3>
            <p className="mt-0.5 text-xs text-gray-400">
              {t('spoolUsage.summary', {
                used: spool.used_weight_g.toFixed(0),
                initial: spool.initial_weight_g.toFixed(0),
                count: events.length,
              })}
            </p>
            {measurement && Math.abs(drift) >= 1 && (
              <p className="mt-1 flex items-center gap-1.5 text-xs text-amber-300/90">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                {t(drift > 0 ? 'spoolUsage.driftUnder' : 'spoolUsage.driftOver', {
                  grams: Math.abs(drift).toFixed(0),
                })}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            title={t('common.close')}
            className="rounded p-1 text-gray-400 transition hover:bg-white/10 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-purple-400" />
          </div>
        ) : events.length === 0 ? (
          <p className="py-8 text-center text-sm text-gray-500">{t('spoolUsage.empty')}</p>
        ) : (
          <div className="mt-3 max-h-80 space-y-1 overflow-y-auto">
            {events.map((event) => {
              const delta = event.delta_weight_g ?? 0;
              const reverted = Boolean(event.meta?.reverted);
              const isReversal = typeof event.meta?.reverts_event_id === 'number';
              const unappliedEstimate =
                event.event_type === 'print_estimate' && event.remaining_weight_g == null;
              const isEstimatedConsumption = event.meta?.consumption_kind === 'estimated';
              const isPrinterConsumption = event.event_type === 'printer_report';
              const balanceAccounting = event.meta?.balance_accounting;
              const isAppliedEstimatedConsumption =
                isEstimatedConsumption
                && delta > 0
                && event.remaining_weight_g != null
                && !reverted
                && !unappliedEstimate
                && balanceAccounting !== 'needs_reconciliation'
                && balanceAccounting !== 'reconciled_by_measurement'
                && !(balanceAccounting === 'already_in_balance' && delta === 0);
              const canRevert =
                !reverted && !isReversal && !unappliedEstimate && event.event_type !== MEASUREMENT && delta > 0;
              const warning = warningFor(event, t);

              return (
                <div key={event.id} className="rounded-lg bg-white/5 px-3 py-2 text-xs">
                  <div className={`flex items-center gap-3 ${reverted ? 'opacity-50' : ''}`}>
                    <span className="w-24 shrink-0 text-gray-500">
                      {new Date(event.created_at).toLocaleString(i18n.language, {
                        day: '2-digit',
                        month: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                    <span
                      className={`w-16 shrink-0 text-right font-medium ${
                        delta > 0 ? 'text-gray-200' : 'text-emerald-300'
                      }`}
                    >
                      {unappliedEstimate || isEstimatedConsumption ? '≈' : delta > 0 ? '−' : '+'}
                      {isEstimatedConsumption && delta > 0 ? '−' : ''}
                      {formatWeight(
                        delta,
                        i18n.language,
                        isEstimatedConsumption || isPrinterConsumption,
                      )} {t('spoolUsage.grams')}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-gray-400">
                      {isReversal
                        ? t('spoolUsage.source.reversal')
                        : event.meta?.reason === 'opening_balance'
                          ? t('spoolUsage.source.opening_balance')
                        : event.event_type === 'print_estimate'
                          ? t('spoolUsage.source.print_estimate')
                        : isEstimatedConsumption
                          ? `${event.device_name ? `${event.device_name} · ` : ''}${t(
                              ESTIMATE_SOURCE_KEYS[String(event.meta?.estimate_source)]
                                ?? 'spoolUsage.source.estimated',
                            )}`
                        : event.device_name ?? t(`spoolUsage.source.${event.event_type}`)}
                      {reverted && ` · ${t('spoolUsage.reverted')}`}
                    </span>
                    {event.remaining_weight_g != null && (
                      <span className="shrink-0 text-gray-500">
                        → {formatWeight(
                          event.remaining_weight_g,
                          i18n.language,
                          isEstimatedConsumption || isPrinterConsumption,
                        )} {t('spoolUsage.grams')}
                      </span>
                    )}
                    {canRevert && (
                      <button
                        type="button"
                        onClick={() => setConfirming(event.id)}
                        title={t('spoolUsage.revert')}
                        className="shrink-0 rounded p-0.5 text-gray-500 transition hover:bg-white/10 hover:text-white"
                      >
                        <Undo2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>

                  {isAppliedEstimatedConsumption && (
                    <p className="mt-1 text-[11px] text-emerald-300/90">
                      {t('spoolUsage.estimatedApplied')}
                    </p>
                  )}

                  {warning && (
                    <p className="mt-1 flex items-center gap-1.5 text-[11px] text-amber-300/80">
                      <AlertTriangle className="h-3 w-3 shrink-0" />
                      {warning}
                    </p>
                  )}

                  {confirming === event.id && (
                    <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-2">
                      <span className="text-gray-300">
                        {t('spoolUsage.confirmRevert', { grams: Math.abs(delta).toFixed(0) })}
                      </span>
                      <span className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => revert.mutate(event.id)}
                          disabled={revert.isPending}
                          className="rounded-lg bg-purple-600 px-3 py-1 font-medium text-white transition hover:bg-purple-500 disabled:opacity-50"
                        >
                          {t('spoolUsage.revert')}
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirming(null)}
                          className="rounded-lg border border-white/15 px-3 py-1 text-gray-300 transition hover:bg-white/10"
                        >
                          {t('common.cancel')}
                        </button>
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </ModalOverlay>
  );
};
