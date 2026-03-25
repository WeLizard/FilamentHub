/** Компонент для переключения синхронизации пресета с OrcaSlicer */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, RefreshCwOff } from 'lucide-react';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { savedPresetsAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { useAuth } from '../contexts/AuthContext';
import type { Preset } from '../types/api';
import type { AxiosError } from 'axios';

interface PresetSyncToggleProps {
  preset: Preset;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  showLabel?: boolean;
}

export const PresetSyncToggle: React.FC<PresetSyncToggleProps> = ({
  preset,
  size = 'md',
  className = '',
  showLabel = false,
}) => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [isToggling, setIsToggling] = useState(false);
  
  // Загружаем user_saved_preset, чтобы получить sync_enabled для этого пользователя
  const { data: savedPresets } = useQuery({
    queryKey: ['saved-presets', user?.id],
    queryFn: () => savedPresetsAPI.list(),
    enabled: !!user?.id,
  });
  
  // Находим сохраненный пресет для получения sync
  const savedPreset = savedPresets?.items.find(sp => sp.preset_id === preset.id);
  const isSyncEnabled = savedPreset?.sync ?? true; // По умолчанию true

  // Размеры иконки
  const iconSizes = {
    sm: 'w-4 h-4',
    md: 'w-5 h-5',
    lg: 'w-6 h-6',
  };

  const iconSize = iconSizes[size];

  // Мутация для переключения синхронизации
  // Используем savedPresetsAPI, так как sync_enabled хранится в user_saved_presets
  const toggleSyncMutation = useMutation({
    mutationFn: async (syncEnabled: boolean) => {
      return savedPresetsAPI.toggleSync(preset.id, syncEnabled);
    },
    onSuccess: (updatedPreset) => {
      // Обновляем кэш сохраненных пресетов и пресетов
      queryClient.invalidateQueries({ queryKey: ['saved-presets', user?.id] });
      queryClient.invalidateQueries({ queryKey: ['presets'] });
      queryClient.invalidateQueries({ queryKey: ['preset', preset.id] });
      queryClient.invalidateQueries({ queryKey: ['filament-presets', preset.filament_id] });
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
      queryClient.invalidateQueries({ queryKey: ['my-presets'] });
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      console.error('Sync toggle error:', error);
      alert(`${t('presetSync.toggleError')}: ${translateApiError(t, error?.response?.data?.detail, t('presetSync.unknownError'))}`);
    },
    onSettled: () => {
      setIsToggling(false);
    },
  });

  // Если пресет не найден в сохраненных, но это пресет пользователя - создаем запись автоматически
  const createSavedPresetMutation = useMutation({
    mutationFn: async () => {
      return savedPresetsAPI.save(preset.id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-presets', user?.id] });
    },
  });

  const handleToggle = async (e: React.MouseEvent) => {
    e.stopPropagation(); // Предотвращаем всплытие события
    if (isToggling || !user) return;

    // Если запись еще не создана, создаем ее сначала
    if (!savedPreset && preset.user_id === user.id) {
      await createSavedPresetMutation.mutateAsync();
      // После создания запись будет доступна, но нужно обновить кэш
      queryClient.invalidateQueries({ queryKey: ['saved-presets', user.id] });
      return;
    }

    setIsToggling(true);
    toggleSyncMutation.mutate(!isSyncEnabled);
  };
  
  // Не показываем компонент, если пользователь не авторизован
  if (!user) {
    return null;
  }
  
  // Не показываем для черновиков — они не скачиваются в OrcaSlicer, toggle бесполезен
  if (!preset.active || !preset.filament_id) {
    return null;
  }

  // Показываем компонент, если это пресет пользователя (созданный или сохраненный)
  // Если запись еще не создана, компонент все равно покажется (при создании пресета запись создается автоматически)
  if (!savedPreset && preset.user_id !== user.id) {
    return null; // Не показываем для чужих пресетов, которые не сохранены
  }

  return (
    <button
      onClick={handleToggle}
      disabled={isToggling}
      className={`flex items-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
      title={
        isSyncEnabled
          ? t('presetSync.enabledTitle')
          : t('presetSync.disabledTitle')
      }
    >
      {isSyncEnabled ? (
        <RefreshCw
          className={`${iconSize} text-blue-400 hover:text-blue-300 transition-colors ${
            isToggling ? 'animate-spin' : ''
          }`}
        />
      ) : (
        <RefreshCwOff
          className={`${iconSize} text-gray-500 hover:text-gray-400 transition-colors ${
            isToggling ? 'opacity-50' : ''
          }`}
        />
      )}
      {showLabel && (
        <span className="text-sm text-gray-300">
          {isSyncEnabled ? t('presetSync.enabled') : t('presetSync.disabled')}
        </span>
      )}
    </button>
  );
};

