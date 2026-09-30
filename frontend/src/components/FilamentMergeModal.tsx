import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { AxiosError } from 'axios';
import { CheckCircle2, GitMerge, Loader2 } from 'lucide-react';
import { filamentsAPI } from '../api/client';
import type { Filament, MergeFilamentSummary } from '../types/api';
import { translateApiError } from '../utils/translateApiError';
import { Dropdown } from './Dropdown';
import { ModalOverlay } from './ModalOverlay';
import { toast } from './Toast';

export function mergeFilamentLabel(filament: MergeFilamentSummary): string {
  return filament.color_name ? `${filament.name} · ${filament.color_name}` : filament.name;
}

export const MergeFilamentOption: React.FC<{ filament: MergeFilamentSummary; likelySame?: boolean }> = ({
  filament,
  likelySame = false,
}) => {
  const { t } = useTranslation();
  return (
    <span className="flex min-w-0 items-center gap-2">
      <span
        className="h-3 w-3 shrink-0 rounded-full border border-white/20"
        style={{ backgroundColor: filament.color_hex || 'transparent' }}
      />
      <span className="truncate">{mergeFilamentLabel(filament)}</span>
      {likelySame && (
        <span className="shrink-0 rounded bg-green-500/20 px-1.5 py-0.5 text-[10px] text-green-300">
          {t('catalogMerge.likelySame')}
        </span>
      )}
    </span>
  );
};

export const MergeContributions: React.FC<{ filament: MergeFilamentSummary }> = ({ filament }) => {
  const { t } = useTranslation();
  return (
    <span className="text-xs text-gray-400">
      {t('catalogMerge.contributions', {
        presets: filament.presets,
        spools: filament.spools,
        reviews: filament.reviews,
      })}
    </span>
  );
};

interface FilamentMergeModalProps {
  filament: Pick<Filament, 'id' | 'name'>;
  onClose: () => void;
  onMerged?: (target: Filament) => void;
}

export const FilamentMergeModal: React.FC<FilamentMergeModalProps> = ({ filament, onClose, onMerged }) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [targetId, setTargetId] = useState<number | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['filament-merge-candidates', filament.id],
    queryFn: () => filamentsAPI.getMergeCandidates(filament.id),
  });

  useEffect(() => {
    if (targetId === null && data) {
      setTargetId(data.candidates.find((item) => item.likely_same)?.id ?? null);
    }
  }, [data, targetId]);

  const target = useMemo(
    () => data?.candidates.find((item) => item.id === targetId) ?? null,
    [data, targetId],
  );

  const mergeMutation = useMutation({
    mutationFn: (id: number) => filamentsAPI.merge(filament.id, id),
    onSuccess: (merged) => {
      queryClient.invalidateQueries({ queryKey: ['brand-filaments'] });
      queryClient.invalidateQueries({ queryKey: ['filaments'] });
      queryClient.invalidateQueries({ queryKey: ['admin-materials'] });
      toast.success(t('catalogMerge.filamentMerged', { name: merged.name }));
      onMerged?.(merged);
      onClose();
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, err.response?.data?.detail, t('catalogMerge.mergeFailed')), 12000);
    },
  });

  const source = data?.source;
  const qrPreserved = Boolean(source?.has_qr_code && target?.has_qr_code);

  return (
    <ModalOverlay
      onClose={onClose}
      closeOnOverlayClick={!mergeMutation.isPending}
      closeOnEscape={!mergeMutation.isPending}
    >
      <div className="w-full max-w-lg rounded-2xl border border-white/20 bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 p-6 shadow-2xl">
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-purple-500/20">
            <GitMerge className="h-5 w-5 text-purple-300" />
          </div>
          <h3 className="text-lg font-bold text-white">{t('catalogMerge.filamentTitle', { name: filament.name })}</h3>
        </div>

        {isLoading && (
          <div className="flex items-center gap-2 py-6 text-gray-300">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>{t('catalogMerge.loading')}</span>
          </div>
        )}

        {error && (
          <p className="text-sm text-red-300">
            {translateApiError(t, (error as AxiosError<{ detail: unknown }>).response?.data?.detail, t('catalogMerge.loadFailed'))}
          </p>
        )}

        {source && data && (
          <div className="space-y-4">
            <p className="text-sm text-gray-300">{t('catalogMerge.filamentExplanation')}</p>
            <div>
              <span className="text-sm text-gray-400">{t('catalogMerge.duplicateHas')} </span>
              <MergeContributions filament={source} />
            </div>

            {data.candidates.length === 0 ? (
              <p className="rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-gray-300">
                {t('catalogMerge.noCandidates')}
              </p>
            ) : (
              <Dropdown
                label={t('catalogMerge.keepFilament')}
                value={targetId ?? ''}
                placeholder={t('catalogMerge.chooseFilament')}
                options={data.candidates.map((item) => ({ value: item.id, label: mergeFilamentLabel(item) }))}
                renderOption={(option) => {
                  const item = data.candidates.find((candidate) => candidate.id === option.value);
                  return item ? <MergeFilamentOption filament={item} likelySame={item.likely_same} /> : option.label;
                }}
                onChange={(value) => setTargetId(Number(value))}
              />
            )}

            {qrPreserved && (
              <p className="flex items-start gap-2 rounded-xl border border-green-500/30 bg-green-500/10 p-3 text-sm text-green-200">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{t('catalogMerge.qrPreserved')}</span>
              </p>
            )}
          </div>
        )}

        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={mergeMutation.isPending}
            className="rounded-xl bg-white/10 px-4 py-2 text-white transition-all hover:bg-white/20 disabled:opacity-50"
          >
            {t('catalogMerge.cancel')}
          </button>
          <button
            type="button"
            onClick={() => targetId && mergeMutation.mutate(targetId)}
            disabled={!targetId || mergeMutation.isPending}
            className="flex items-center gap-2 rounded-xl bg-purple-600 px-4 py-2 text-white transition-all hover:bg-purple-700 disabled:opacity-50"
          >
            {mergeMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitMerge className="h-4 w-4" />}
            <span>{t('catalogMerge.merge')}</span>
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
};
