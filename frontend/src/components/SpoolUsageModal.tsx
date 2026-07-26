import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Loader2, X } from 'lucide-react';

import { spoolsAPI } from '../api/client';
import type { UserSpool } from '../api/client';
import { ModalOverlay } from './ModalOverlay';

interface SpoolUsageModalProps {
  spool: UserSpool;
  isOpen: boolean;
  onClose: () => void;
}

export const SpoolUsageModal: React.FC<SpoolUsageModalProps> = ({ spool, isOpen, onClose }) => {
  const { t, i18n } = useTranslation();

  const { data: events = [], isLoading } = useQuery({
    queryKey: ['spool-usage', spool.id],
    queryFn: () => spoolsAPI.usage(spool.id),
    enabled: isOpen,
  });

  if (!isOpen) return null;

  const title = spool.filament?.name ?? t('profilePage.spoolNoFilament');

  return (
    <ModalOverlay onClose={onClose}>
      <div className="w-full max-w-lg rounded-2xl border border-white/20 bg-gray-900 p-5 shadow-xl">
        <div className="mb-1 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate text-base font-semibold text-white">
              {t('spoolUsage.title', { name: title })}
            </h3>
            <p className="mt-0.5 text-xs text-gray-400">
              {t('spoolUsage.summary', {
                used: spool.used_weight_g.toFixed(0),
                initial: spool.initial_weight_g.toFixed(0),
                count: events.length,
              })}
            </p>
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
              return (
                <div
                  key={event.id}
                  className="flex items-center justify-between gap-3 rounded-lg bg-white/5 px-3 py-2 text-xs"
                >
                  <span className="w-28 shrink-0 text-gray-500">
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
                    {delta > 0 ? '−' : '+'}
                    {Math.abs(delta).toFixed(0)} {t('spoolUsage.grams')}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-gray-400">
                    {event.device_name ?? t(`spoolUsage.source.${event.event_type}`)}
                  </span>
                  {event.remaining_weight_g != null && (
                    <span className="shrink-0 text-gray-500">
                      → {event.remaining_weight_g.toFixed(0)} {t('spoolUsage.grams')}
                    </span>
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
