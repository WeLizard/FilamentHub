/** Модалка для обработки удалённых пресетов */

import { useState, useEffect } from 'react';
import { X, RotateCcw, Trash2, SkipForward, CheckCircle2 } from 'lucide-react';
import { ModalOverlay } from './ModalOverlay';
import { orcaslicerDeletedPresetsAPI, notificationsAPI } from '../api/client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Notification } from '../types/api';

import { useTranslation } from 'react-i18next';
import { translateApiError } from '../utils/translateApiError';

interface DeletedPreset {
  preset_id: number;
  preset_name: string;
  bundle_preset_name?: string | null;
  is_created: boolean;
  is_saved: boolean;
}

interface DeletedPresetsModalProps {
  isOpen: boolean;
  onClose: () => void;
  notification: Notification;
}

export const DeletedPresetsModal: React.FC<DeletedPresetsModalProps> = ({
  isOpen,
  onClose,
  notification: initialNotification,
}) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedPresetIds, setSelectedPresetIds] = useState<Set<number>>(new Set());
  const [action, setAction] = useState<'restore' | 'delete' | 'skip' | null>(null);
  const [saveRule, setSaveRule] = useState(false);
  // Локальное состояние для обработанных пресетов (оптимистичное обновление)
  const [processedPresetIds, setProcessedPresetIds] = useState<Set<number>>(new Set());
  // Сообщение об успешной обработке
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  // Получаем актуальное уведомление из кэша после обновления
  // Используем useQuery для получения актуальных данных
  const { data: notificationsData } = useQuery({
    queryKey: ['notifications', initialNotification.user_id],
    queryFn: () => notificationsAPI.list({ page: 1, size: 50 }),
    enabled: isOpen && !!initialNotification.user_id,
    refetchInterval: false,
  });
  
  const notification = notificationsData?.items?.find((n) => n.id === initialNotification.id) || initialNotification;

  // Убираем обработанные пресеты из списка
  const allDeletedPresets: DeletedPreset[] = notification.extra_data?.deleted_presets || [];
  const deletedPresets: DeletedPreset[] = allDeletedPresets.filter(
    (p) => !processedPresetIds.has(p.preset_id)
  );
  
  const createdCount = deletedPresets.filter((p) => p.is_created).length;
  const savedCount = deletedPresets.filter((p) => p.is_saved).length;

  // Инициализируем выбранные пресеты (все по умолчанию) при открытии или изменении списка
  useEffect(() => {
    if (isOpen && deletedPresets.length > 0) {
      // Проверяем, что выбранные ID все еще существуют в списке (не обработаны)
      const validPresetIds = new Set(deletedPresets.map((p) => p.preset_id));
      const currentSelectedIds = Array.from(selectedPresetIds).filter((id) => validPresetIds.has(id));
      
      // Если не выбрано ничего или выбраны только несуществующие ID, выбираем все
      if (currentSelectedIds.length === 0 && validPresetIds.size > 0) {
        setSelectedPresetIds(new Set(validPresetIds));
      } else {
        // Обновляем выбранные ID, убирая обработанные
        setSelectedPresetIds(new Set(currentSelectedIds));
      }
    }
  }, [isOpen, deletedPresets.length, notification.id]);

  // Сбрасываем обработанные пресеты при закрытии модалки
  useEffect(() => {
    if (!isOpen) {
      setProcessedPresetIds(new Set());
      setSelectedPresetIds(new Set());
      setAction(null);
      setSaveRule(false);
      setSuccessMessage(null);
    }
  }, [isOpen]);

  if (!isOpen || !notification.extra_data) {
    if (!isOpen) return null;
    console.error(t('deletedPresetsModal.extra_data_not_found'));
    return null;
  }

  const handleTogglePreset = (presetId: number) => {
    const newSelected = new Set(selectedPresetIds);
    if (newSelected.has(presetId)) {
      newSelected.delete(presetId);
    } else {
      newSelected.add(presetId);
    }
    setSelectedPresetIds(newSelected);
  };

  const handleSelectAll = () => {
    const allPresetIds = new Set(deletedPresets.map((p) => p.preset_id));
    const allSelected = allPresetIds.size > 0 && 
                        Array.from(allPresetIds).every((id) => selectedPresetIds.has(id));
    
    if (allSelected) {
      setSelectedPresetIds(new Set());
    } else {
      setSelectedPresetIds(new Set(allPresetIds));
    }
  };

  const handleActionMutation = useMutation({
    mutationFn: async (actionData: {
      action: 'restore' | 'delete' | 'skip';
      preset_ids?: number[] | null;
      apply_to_all?: boolean;
      save_rule?: boolean;
    }) => {
      return orcaslicerDeletedPresetsAPI.handleAction(notification.id, actionData);
    },
    onSuccess: async (response) => {
      // Оптимистичное обновление - сразу удаляем обработанные пресеты из списка
      const processedIds = Array.from(selectedPresetIds);
      setProcessedPresetIds((prev) => {
        const newSet = new Set(prev);
        processedIds.forEach((id) => newSet.add(id));
        return newSet;
      });
      
      // Показываем сообщение об успехе
      const count = processedIds.length;
      const actionLabels = {
        restore: t('deletedPresetsModal.success_message_restore_other', {count: count}),
        delete: t('deletedPresetsModal.success_message_delete_other', {count: count}),
        skip: t('deletedPresetsModal.success_message_skip_other', {count: count}),
      };
      
      if (count === 1) {
        actionLabels.restore = t('deletedPresetsModal.success_message_restore_one');
        actionLabels.delete = t('deletedPresetsModal.success_message_delete_one');
        actionLabels.skip = t('deletedPresetsModal.success_message_skip_one');
      }

      const currentAction = action; // Сохраняем action до сброса
      const actionLabel = currentAction ? actionLabels[currentAction] || t('deletedPresetsModal.success_message_skip_other', {count: count}) : t('deletedPresetsModal.success_message_skip_other', {count: count});
      
      setSuccessMessage(`${actionLabel}`);
      
      // Убираем сообщение через 3 секунды
      setTimeout(() => setSuccessMessage(null), 3000);
      
      // Обновляем локальное состояние - сбрасываем выбор и действие
      setSelectedPresetIds(new Set());
      setAction(null);
      setSaveRule(false);
      
      // Обновляем уведомления в фоне
      await queryClient.invalidateQueries({ queryKey: ['notifications'] });
      await queryClient.refetchQueries({ queryKey: ['notifications', notification.user_id] });
      
      // Проверяем, остались ли необработанные пресеты
      const allRemainingPresets = allDeletedPresets.filter(
        (p) => !processedPresetIds.has(p.preset_id) && !processedIds.includes(p.preset_id)
      );
      
      // Если все пресеты обработаны, удаляем уведомление
      if (allRemainingPresets.length === 0) {
        try {
          await notificationsAPI.delete(notification.id);
          await queryClient.invalidateQueries({ queryKey: ['notifications'] });
          // Закрываем модалку после небольшой задержки
          setTimeout(() => {
            onClose();
          }, 1500);
              } catch (error) {
                console.error(t('deletedPresetsModal.error_deleting_notification'), error);        }
      }
    },
    onError: (error: any) => {
      const msg = translateApiError(t, error?.response?.data?.detail, t('deletedPresetsModal.error_unknown'));
      console.error(t('deletedPresetsModal.error_handling_action', {message: msg}));
      alert(t('deletedPresetsModal.error_handling_action', {message: msg}));
    },
  });

  // Закрываем модалку, если все пресеты обработаны
  useEffect(() => {
    if (isOpen && deletedPresets.length === 0) {
      // Небольшая задержка для плавного закрытия
      const timer = setTimeout(() => {
        onClose();
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [isOpen, deletedPresets.length, onClose]);

  const handleApplyAction = () => {
    if (!action) {
      console.warn(t('deletedPresetsModal.warning_no_action_selected'));
      return;
    }

    if (selectedPresetIds.size === 0) {
      console.warn(t('deletedPresetsModal.warning_no_presets_selected'));
      alert(t('deletedPresetsModal.warning_no_presets_selected'));
      return;
    }

    const presetIds = Array.from(selectedPresetIds);
    const applyToAll = presetIds.length === deletedPresets.length;



    handleActionMutation.mutate({
      action,
      preset_ids: applyToAll ? null : presetIds,
      apply_to_all: applyToAll,
      save_rule: saveRule,
    });
  };

  // Обработка закрытия модалки - автоматически применяем "skip" для всех необработанных пресетов
  const handleCloseWithAutoSkip = async () => {
    // Если есть необработанные пресеты, применяем "skip" (оставить как есть)
    if (deletedPresets.length > 0) {
      const unprocessedPresetIds = deletedPresets.map((p) => p.preset_id);
      
      try {
        await orcaslicerDeletedPresetsAPI.handleAction(notification.id, {
          action: 'skip',
          preset_ids: unprocessedPresetIds,
          apply_to_all: false,
          save_rule: false,
        });
        
        // Обновляем уведомления
        await queryClient.invalidateQueries({ queryKey: ['notifications'] });
        await queryClient.refetchQueries({ queryKey: ['notifications', notification.user_id] });
        
        // Если все пресеты были необработанными, удаляем уведомление
        if (unprocessedPresetIds.length === allDeletedPresets.length) {
          await notificationsAPI.delete(notification.id);
          await queryClient.invalidateQueries({ queryKey: ['notifications'] });
        }
      } catch (error) {
        console.error(t('deletedPresetsModal.error_auto_handling_presets'), error);
      }
    }
    
    onClose();
  };

  const getActionButton = (actionType: 'restore' | 'delete' | 'skip') => {
    const configs = {
      restore: {
        icon: <RotateCcw className="w-4 h-4" />,
        label: t('deletedPresetsModal.action_restore_label'),
        bg: 'bg-blue-600 hover:bg-blue-700',
        shortDescription: t('deletedPresetsModal.action_restore_short'),
        fullDescription: t('deletedPresetsModal.action_restore_full'),
      },
      delete: {
        icon: <Trash2 className="w-4 h-4" />,
        label: t('deletedPresetsModal.action_delete_label'),
        bg: 'bg-red-600 hover:bg-red-700',
        shortDescription: t('deletedPresetsModal.action_delete_short'),
        fullDescription: t('deletedPresetsModal.action_delete_full'),
      },
      skip: {
        icon: <SkipForward className="w-4 h-4" />,
        label: t('deletedPresetsModal.action_skip_label'),
        bg: 'bg-gray-600 hover:bg-gray-700',
        shortDescription: t('deletedPresetsModal.action_skip_short'),
        fullDescription: t('deletedPresetsModal.action_skip_full'),
      },
    };

    const config = configs[actionType];
    const isSelected = action === actionType;

    return (
      <button
        onClick={() => setAction(actionType)}
        className={`flex flex-col items-start space-y-2 px-4 py-4 rounded-lg transition-all text-left h-full ${
          isSelected
            ? `${config.bg} text-white border-2 border-white/50`
            : 'bg-white/10 hover:bg-white/20 text-gray-300 border-2 border-transparent'
        }`}
      >
        <div className="flex items-center space-x-2 w-full">
          {config.icon}
          <span className="font-semibold text-sm">{config.label}</span>
        </div>
        <span className={`text-xs leading-relaxed ${isSelected ? 'text-white/90' : 'text-gray-400'}`}>
          {config.shortDescription}
        </span>
      </button>
    );
  };

  return (
    <ModalOverlay onClose={handleCloseWithAutoSkip} closeOnOverlayClick={!handleActionMutation.isPending}>
      <div
        className="bg-gradient-to-br from-purple-900 to-indigo-900 rounded-2xl max-w-4xl w-full overflow-hidden flex flex-col border border-white/20 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-white/10">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-yellow-500/20 rounded-lg flex items-center justify-center">
                <div className="text-yellow-400">
                  <X className="w-5 h-5" />
                </div>
              </div>
              <div>
                <h3 className="text-xl font-bold text-white">{t('deletedPresetsModal.title')}</h3>
                <p className="text-sm text-gray-400 mt-1">
                  {t('deletedPresetsModal.subtitle', { count: deletedPresets.length })}
                </p>
              </div>
            </div>
            <button
              onClick={handleCloseWithAutoSkip}
              disabled={handleActionMutation.isPending}
              className="text-gray-400 hover:text-white transition-colors disabled:opacity-50"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <div className="p-6 overflow-y-auto flex-1 max-h-[60vh]">
            {/* Success Message */}
            {successMessage && (
              <div className="mb-4 p-3 bg-green-500/20 border border-green-500/50 rounded-lg">
                <p className="text-sm text-green-300 font-medium">
                  ✓ {successMessage}
                </p>
              </div>
            )}
            
            {/* Stats */}
            <div className="mb-4 p-3 bg-white/5 rounded-lg">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-300">{t('deletedPresetsModal.stats_total')}</span>
                <span className="text-white font-semibold">{deletedPresets.length}</span>
              </div>
              {createdCount > 0 && (
                <div className="flex items-center justify-between text-sm mt-1">
                  <span className="text-gray-300">{t('deletedPresetsModal.stats_created')}</span>
                  <span className="text-blue-400 font-semibold">{createdCount}</span>
                </div>
              )}
              {savedCount > 0 && (
                <div className="flex items-center justify-between text-sm mt-1">
                  <span className="text-gray-300">{t('deletedPresetsModal.stats_saved')}</span>
                  <span className="text-green-400 font-semibold">{savedCount}</span>
                </div>
              )}
            </div>

            {/* Presets List */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-semibold text-white">{t('deletedPresetsModal.select_presets')}</h4>
                {deletedPresets.length > 0 && (
                  <button
                    onClick={handleSelectAll}
                    className="text-sm text-purple-400 hover:text-purple-300 transition-colors"
                  >
                    {Array.from(deletedPresets.map((p) => p.preset_id)).every((id) => selectedPresetIds.has(id))
                      ? t('deletedPresetsModal.deselect_all')
                      : t('deletedPresetsModal.select_all')}
                  </button>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 max-h-64 overflow-y-auto">
                {deletedPresets.map((preset) => {
                  const isSelected = selectedPresetIds.has(preset.preset_id);
                  return (
                    <label
                      key={preset.preset_id}
                      className={`flex items-start space-x-2 p-3 rounded-lg cursor-pointer transition-all ${
                        isSelected ? 'bg-purple-500/20 border border-purple-500/50' : 'bg-white/5 hover:bg-white/10'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => handleTogglePreset(preset.preset_id)}
                        className="mt-1 w-4 h-4 flex-shrink-0 rounded border-gray-400 text-purple-600 focus:ring-purple-500"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-1">
                          <span className="text-sm font-medium text-white break-words">{preset.preset_name}</span>
                          {preset.is_created && (
                            <span className="px-1.5 py-0.5 bg-blue-500/20 text-blue-400 text-xs rounded flex-shrink-0">
                              {t('deletedPresetsModal.preset_created')}
                            </span>
                          )}
                          {preset.is_saved && (
                            <span className="px-1.5 py-0.5 bg-green-500/20 text-green-400 text-xs rounded flex-shrink-0">
                              {t('deletedPresetsModal.preset_saved')}
                            </span>
                          )}
                        </div>
                        {preset.bundle_preset_name && (
                          <p className="text-xs text-gray-400 mt-1 break-words">
                            {t('deletedPresetsModal.orcaslicer_prefix')} {preset.bundle_preset_name}
                          </p>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>

            {/* Action Selection */}
            <div className="mb-4">
              <h4 className="text-sm font-semibold text-white mb-3">{t('deletedPresetsModal.action_selection_title')}</h4>
              <div className="grid grid-cols-3 gap-3">
                {getActionButton('restore')}
                {getActionButton('delete')}
                {getActionButton('skip')}
              </div>
              {action && (
                <div className="mt-3 p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                  <p className="text-sm text-blue-300 font-medium mb-1">
                    {action === 'restore' && t('deletedPresetsModal.action_restore_label')}
                    {action === 'delete' && t('deletedPresetsModal.action_delete_label')}
                    {action === 'skip' && t('deletedPresetsModal.action_skip_label')}
                  </p>
                  <p className="text-xs text-blue-200/80">
                    {action === 'restore' && t('deletedPresetsModal.action_restore_full')}
                    {action === 'delete' && t('deletedPresetsModal.action_delete_full')}
                    {action === 'skip' && t('deletedPresetsModal.action_skip_full')}
                  </p>
                </div>
              )}
            </div>

            {/* Save Rule */}
            {action && (
              <div className="mb-4">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={saveRule}
                    onChange={(e) => setSaveRule(e.target.checked)}
                    className="w-4 h-4 rounded border-gray-400 text-purple-600 focus:ring-purple-500"
                  />
                  <span className="text-sm text-gray-300">
                    {t('deletedPresetsModal.save_rule_checkbox')}
                  </span>
                </label>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end space-x-3 p-6 border-t border-white/10">
            <button
              onClick={handleCloseWithAutoSkip}
              disabled={handleActionMutation.isPending}
              className="px-6 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t('deletedPresetsModal.close_button')}
            </button>
            <button
              onClick={handleApplyAction}
              disabled={!action || selectedPresetIds.size === 0 || handleActionMutation.isPending}
              className="px-6 py-2.5 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
            >
              {handleActionMutation.isPending ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>{t('deletedPresetsModal.executing_button')}</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4" />
                  <span>{t('deletedPresetsModal.apply_button')}</span>
                </>
              )}
            </button>
          </div>
        </div>
    </ModalOverlay>
  );
};



