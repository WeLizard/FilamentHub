/** Контрол library scope пресета: экспорт для всех принтеров или под выбранные принтер-профили */

import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from './Toast';
import { Crosshair } from 'lucide-react';
import { printerProfilesAPI, savedPresetsAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { notifyProfileChanged } from '../utils/pluginBridge';
import { useAuth } from '../contexts/AuthContext';
import { Dropdown } from './Dropdown';
import type { Preset } from '../types/api';
import type { AxiosError } from 'axios';

/** Активные принтер-профили текущего пользователя (общий кэш с ProfilePage). */
export function useMyActivePrinterProfiles() {
  const { user } = useAuth();
  const { data } = useQuery({
    queryKey: ['printer-profiles', user?.id],
    queryFn: () =>
      printerProfilesAPI.list({
        owner_user_id: user!.id,
        page: 1,
        size: 50,
        active_only: false,
      }),
    enabled: !!user?.id,
  });
  return (data?.items ?? []).filter(p => p.active);
}

interface PresetScopeControlProps {
  preset: Preset;
  className?: string;
}

export const PresetScopeControl: React.FC<PresetScopeControlProps> = ({ preset, className = '' }) => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  // Запись user_saved_preset несёт scope/цели текущего пользователя
  const { data: savedPresets } = useQuery({
    queryKey: ['saved-presets', user?.id],
    queryFn: () => savedPresetsAPI.list(),
    enabled: !!user?.id,
  });
  const savedPreset = savedPresets?.items.find(sp => sp.preset_id === preset.id);

  const activeProfiles = useMyActivePrinterProfiles();

  const updateScopeMutation = useMutation({
    mutationFn: async (targetIds: number[]) => savedPresetsAPI.updateScope(preset.id, targetIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-presets', user?.id] });
      // Экспорт пресета меняется — плагин пересинхронизирует изменившийся JSON
      notifyProfileChanged();
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, error?.response?.data?.detail, t('presetScope.updateError')));
    },
  });

  // Нет записи (чужой несохранённый пресет) или нет профилей — целиться не во что
  if (!user || !savedPreset || activeProfiles.length === 0) {
    return null;
  }

  const selectedIds = savedPreset.target_printer_profile_ids.filter(id =>
    activeProfiles.some(profile => profile.id === id)
  );

  const options = activeProfiles.map(profile => ({ value: profile.id, label: profile.name }));

  const handleMultiChange = (values: (string | number)[]) => {
    if (updateScopeMutation.isPending) return;
    updateScopeMutation.mutate(values.map(Number));
  };

  return (
    <div className={`flex items-center gap-2 ${className}`} title={t('presetScope.tooltip')}>
      <Crosshair className="w-4 h-4 text-gray-400 flex-shrink-0" />
      <span className="text-xs text-gray-400 whitespace-nowrap">{t('presetScope.label')}</span>
      <Dropdown
        value=""
        onChange={() => {}}
        multiple
        selectedValues={selectedIds}
        onMultiChange={handleMultiChange}
        options={options}
        placeholder={t('presetScope.allPrinters')}
        size="sm"
        className="w-52"
        disabled={updateScopeMutation.isPending}
        maxHeight="max-h-48"
      />
    </div>
  );
};
