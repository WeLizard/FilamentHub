/** Карточки источников данных для каталога принтеров FilamentHub.
 *
 * Сегодня единственный источник — OrcaSlicer (resources/profiles).
 * В будущем сюда добавятся PrusaSlicer / Cura / Bambu Studio
 * как отдельные карточки в этом же контейнере.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Database, Upload, Loader2, CheckCircle, AlertCircle, Package } from 'lucide-react';
import { adminAPI } from '../../api/client';
import { translateApiError } from '../../utils/translateApiError';
import type { AxiosError } from 'axios';

export const AdminCatalogSources: React.FC = () => {
  const { t } = useTranslation();
  return (
    <div className="space-y-4 mb-6">
      <div className="flex items-center gap-2">
        <Database className="w-5 h-5 text-indigo-300" />
        <h3 className="text-lg font-bold text-white">{t('adminCatalogSources.title')}</h3>
      </div>
      <p className="text-sm text-gray-400 -mt-2">{t('adminCatalogSources.description')}</p>

      <OrcaSlicerSourceCard />
      {/* Future: PrusaSlicerSourceCard, CuraSourceCard, BambuStudioSourceCard */}
    </div>
  );
};

const OrcaSlicerSourceCard: React.FC = () => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [lastSummary, setLastSummary] = useState<Record<string, number> | null>(null);

  const { data: info, isLoading: isLoadingInfo, refetch } = useQuery({
    queryKey: ['admin-catalog-source-orca-info'],
    queryFn: adminAPI.getCatalogSourceOrcaInfo,
  });

  const importMutation = useMutation({
    mutationFn: adminAPI.importCatalogSourceOrca,
    onSuccess: (result) => {
      setError(null);
      setLastSummary(result.summary);
      refetch();
      queryClient.invalidateQueries({ queryKey: ['admin-printers'] });
      queryClient.invalidateQueries({ queryKey: ['printers'] });
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setError(translateApiError(t, err.response?.data?.detail, t('adminCatalogSources.orca.importError')));
      setLastSummary(null);
    },
  });

  const bundleAvailable = info?.bundle.exists === true;

  return (
    <div className="bg-gradient-to-br from-indigo-900/30 to-purple-900/20 border border-indigo-500/30 rounded-2xl p-6">
      <div className="flex items-start gap-4">
        <div className="p-3 bg-indigo-600/30 rounded-xl shrink-0">
          <Package className="w-6 h-6 text-indigo-300" />
        </div>

        <div className="flex-1 min-w-0">
          <h4 className="text-base font-bold text-white mb-1">{t('adminCatalogSources.orca.title')}</h4>
          <p className="text-sm text-gray-300 mb-4">{t('adminCatalogSources.orca.description')}</p>

          {/* Stats */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
            <StatBox
              icon={Package}
              label={t('adminCatalogSources.orca.bundleStatus')}
              value={
                isLoadingInfo
                  ? '…'
                  : bundleAvailable
                    ? t('adminCatalogSources.orca.bundleReady', { size: info?.bundle.size_mb ?? '?' })
                    : t('adminCatalogSources.orca.bundleMissing')
              }
              tone={bundleAvailable ? 'good' : 'warn'}
            />
            <StatBox
              icon={Database}
              label={t('adminCatalogSources.orca.bundleVendors')}
              value={isLoadingInfo ? '…' : String(info?.bundle.vendor_count ?? 0)}
            />
            <StatBox
              icon={CheckCircle}
              label={t('adminCatalogSources.orca.systemPrinters')}
              value={
                isLoadingInfo
                  ? '…'
                  : `${info?.catalog.printers_system ?? 0} / ${info?.catalog.printers_total ?? 0}`
              }
            />
          </div>

          {error && (
            <div className="flex items-start gap-2 p-3 mb-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-200">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {lastSummary && !error && (
            <div className="p-3 mb-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-sm text-emerald-200">
              <div className="font-semibold mb-1">{t('adminCatalogSources.orca.importSuccess')}</div>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
                {Object.entries(lastSummary).map(([k, v]) => (
                  <div key={k}>
                    <span className="text-emerald-300/70">{k}:</span>{' '}
                    <span className="font-mono">{v}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={() => importMutation.mutate()}
            disabled={!bundleAvailable || importMutation.isPending}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
          >
            {importMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                {t('adminCatalogSources.orca.importing')}
              </>
            ) : (
              <>
                <Upload className="w-4 h-4" />
                {t('adminCatalogSources.orca.importButton')}
              </>
            )}
          </button>
          {!bundleAvailable && !isLoadingInfo && (
            <p className="text-xs text-amber-300 mt-2">{t('adminCatalogSources.orca.bundleMissingHint')}</p>
          )}
        </div>
      </div>
    </div>
  );
};

interface StatBoxProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  tone?: 'good' | 'warn' | 'neutral';
}

const StatBox: React.FC<StatBoxProps> = ({ icon: Icon, label, value, tone = 'neutral' }) => {
  const colorClass =
    tone === 'good'
      ? 'text-emerald-300'
      : tone === 'warn'
        ? 'text-amber-300'
        : 'text-white';
  return (
    <div className="p-3 bg-black/20 rounded-lg border border-white/5">
      <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
        <Icon className="w-3.5 h-3.5" />
        <span>{label}</span>
      </div>
      <div className={`font-semibold text-sm ${colorClass}`}>{value}</div>
    </div>
  );
};
