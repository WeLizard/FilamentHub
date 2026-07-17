/** Контрол library scope пресета: экспорт для всех принтеров или под конкретный принтер-профиль */

import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from './Toast';
import { Crosshair } from 'lucide-react';
import { printerProfilesAPI, savedPresetsAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { notifyProfileChanged } from '../utils/pluginBridge';
import { useAuth } from '../contexts/AuthContext';
import { Dropdown } from './Dropdown';
import type { Preset, PresetLibraryScope } from '../types/api';
import type { AxiosError } from 'axios';

const UNSCOPED_VALUE = 'unscoped';

interface PresetScopeControlProps {
  preset: Preset;
  className?: string;
}

export const PresetScopeControl: React.FC<PresetScopeControlProps> = ({ preset, className = '' }) => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  // Запись user_saved_preset несёт scope/target текущего пользователя
  const { data: savedPresets } = useQuery({
    queryKey: ['saved-presets', user?.id],
    queryFn: () => savedPresetsAPI.list(),
    enabled: !!user?.id,
  });
  const savedPreset = savedPresets?.items.find(sp => sp.preset_id === preset.id);

  // Тот же ключ, что в ProfilePage — кэш общий, лишнего запроса нет
  const { data: printerProfilesData } = useQuery({
    queryKey: ['printer-profiles', user?.id],
    queryFn: () =>
      printerProfilesAPI.list({
        owner_user_id: user!.id,
        page: 1,
        size: 50,
        active_only: false,
      }),
    enabled: !!user?.id && !!savedPreset,
  });
  const activeProfiles = (printerProfilesData?.items ?? []).filter(p => p.active);

  const updateScopeMutation = useMutation({
    mutationFn: async (params: { scope: PresetLibraryScope; targetId: number | null }) =>
      savedPresetsAPI.updateScope(preset.id, params.scope, params.targetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-presets', user?.id] });
      // Экспорт пресета меняется — плагин пересинхронизирует набор
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

  const currentValue =
    savedPreset.scope === 'targeted' && savedPreset.target_printer_profile_id != null
      ? savedPreset.target_printer_profile_id
      : UNSCOPED_VALUE;

  const options = [
    { value: UNSCOPED_VALUE, label: t('presetScope.allPrinters') },
    ...activeProfiles.map(profile => ({ value: profile.id, label: profile.name })),
  ];

  const handleChange = (value: string | number) => {
    if (updateScopeMutation.isPending) return;
    if (value === UNSCOPED_VALUE || value === '') {
      if (savedPreset.scope !== 'unscoped') {
        updateScopeMutation.mutate({ scope: 'unscoped', targetId: null });
      }
      return;
    }
    const targetId = Number(value);
    if (targetId !== savedPreset.target_printer_profile_id || savedPreset.scope !== 'targeted') {
      updateScopeMutation.mutate({ scope: 'targeted', targetId });
    }
  };

  return (
    <div className={`flex items-center gap-2 ${className}`} title={t('presetScope.tooltip')}>
      <Crosshair className="w-4 h-4 text-gray-400 flex-shrink-0" />
      <span className="text-xs text-gray-400 whitespace-nowrap">{t('presetScope.label')}</span>
      <Dropdown
        value={currentValue}
        options={options}
        onChange={handleChange}
        size="sm"
        className="w-52"
        disabled={updateScopeMutation.isPending}
        maxHeight="max-h-48"
      />
    </div>
  );
};
