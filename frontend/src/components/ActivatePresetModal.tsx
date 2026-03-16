import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Zap, Search, Loader2 } from 'lucide-react';
import { ModalOverlay } from './ModalOverlay';
import { toast } from './Toast';
import { presetsAPI, filamentsAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import type { Preset, Filament } from '../types/api';

interface ActivatePresetModalProps {
  preset: Preset;
  onClose: () => void;
}

export const ActivatePresetModal: React.FC<ActivatePresetModalProps> = ({ preset, onClose }) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [selectedFilamentId, setSelectedFilamentId] = useState<number | null>(null);

  const enrichment = (preset as any).orcaslicer_settings?.enrichment;
  const isOrphaned = (preset as any).orcaslicer_settings?.orphaned;

  const { data: filamentsData, isLoading: isLoadingFilaments } = useQuery({
    queryKey: ['filaments-for-activate', search],
    queryFn: () => filamentsAPI.list({ search: search || undefined, size: 20 }),
  });

  const filaments: Filament[] = filamentsData?.items || [];

  const activateMutation = useMutation({
    mutationFn: (filamentId: number) => presetsAPI.activate(preset.id, filamentId),
    onSuccess: () => {
      toast.success(t('profilePage.presetActivated'));
      queryClient.invalidateQueries({ queryKey: ['presets'] });
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
      queryClient.invalidateQueries({ queryKey: ['my-presets'] });
      queryClient.invalidateQueries({ queryKey: ['my-presets-stats'] });
      queryClient.invalidateQueries({ queryKey: ['presets-stats'] });
      onClose();
    },
    onError: (error: any) => {
      const detail = error?.response?.data?.detail;
      toast.error(translateApiError(t, detail, t('common.error')));
    },
  });

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-gray-900 rounded-2xl p-6 border border-white/20 max-w-lg w-full">
        <h3 className="text-lg font-semibold text-white mb-2 flex items-center gap-2">
          <Zap className="w-5 h-5 text-green-400" />
          {t('profilePage.activatePresetTitle')}
        </h3>

        <p className="text-gray-400 text-sm mb-4">
          {t('profilePage.activatePresetDesc')}
        </p>

        {/* Enrichment info */}
        {enrichment && (
          <div className="bg-white/5 rounded-lg p-3 mb-4 text-sm space-y-1">
            <div className="flex justify-between">
              <span className="text-gray-400">{t('profilePage.enrichmentConfidence')}:</span>
              <span className={enrichment.confidence >= 0.8 ? 'text-green-400' : enrichment.confidence >= 0.5 ? 'text-yellow-400' : 'text-orange-400'}>
                {enrichment.confidence >= 0.8
                  ? t('profilePage.enrichmentConfidenceHigh')
                  : enrichment.confidence >= 0.5
                    ? t('profilePage.enrichmentConfidenceMedium')
                    : t('profilePage.enrichmentConfidenceLow')}
              </span>
            </div>
            {enrichment.material_type && (
              <div className="text-cyan-400">
                {t('profilePage.materialDetected', { type: enrichment.material_type })}
              </div>
            )}
            {enrichment.filled_fields?.length > 0 && (
              <div className="text-gray-500">
                {t('profilePage.fieldsAutoFilled', { count: enrichment.filled_fields.length })}
              </div>
            )}
          </div>
        )}

        {isOrphaned && (
          <div className="bg-purple-600/10 border border-purple-500/30 rounded-lg p-3 mb-4 text-sm text-purple-300">
            {t('profilePage.orphanedTooltip')}
          </div>
        )}

        {/* Preset summary */}
        <div className="bg-white/5 rounded-lg p-3 mb-4">
          <div className="font-medium text-white mb-1">{preset.name}</div>
          <div className="text-sm text-gray-400 grid grid-cols-2 gap-1">
            <span>{preset.extruder_temp}°C / {preset.bed_temp}°C</span>
            <span>{preset.print_speed} mm/s</span>
          </div>
        </div>

        {/* Filament search */}
        <div className="relative mb-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('profilePage.selectFilament')}
            className="w-full pl-10 pr-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* Filament list */}
        <div className="max-h-48 overflow-y-auto space-y-1 mb-4">
          {isLoadingFilaments && (
            <div className="flex justify-center py-4">
              <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
            </div>
          )}
          {filaments.map((f) => (
            <button
              key={f.id}
              onClick={() => setSelectedFilamentId(f.id)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-all ${
                selectedFilamentId === f.id
                  ? 'bg-blue-600/30 border border-blue-500/50 text-white'
                  : 'bg-white/5 hover:bg-white/10 text-gray-300'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="truncate">{f.name}</span>
                <span className="text-xs text-gray-500 flex-shrink-0 ml-2">{f.material_type}</span>
              </div>
            </button>
          ))}
          {!isLoadingFilaments && filaments.length === 0 && search && (
            <p className="text-gray-500 text-sm text-center py-3">{t('common.noResults')}</p>
          )}
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-white text-sm transition-all"
          >
            {t('common.cancel')}
          </button>
          <button
            onClick={() => selectedFilamentId && activateMutation.mutate(selectedFilamentId)}
            disabled={!selectedFilamentId || activateMutation.isPending}
            className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-white text-sm transition-all flex items-center gap-2"
          >
            {activateMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Zap className="w-4 h-4" />
            )}
            {t('profilePage.activatePreset')}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
};
