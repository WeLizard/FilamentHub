/** Модалка для обработки удалённых пресетов */

import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X, RotateCcw, Trash2, SkipForward, CheckCircle2 } from 'lucide-react';
import { useHeaderVisible } from '../hooks/useHeaderVisible';
import { orcaslicerDeletedPresetsAPI, notificationsAPI } from '../api/client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Notification } from '../types/api';

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
  const isHeaderVisible = useHeaderVisible();
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

  if (!isOpen || !notification.extra_data) return null;

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
      console.log('Действие успешно применено:', response);
      
      // Оптимистичное обновление - сразу удаляем обработанные пресеты из списка
      const processedIds = Array.from(selectedPresetIds);
      setProcessedPresetIds((prev) => {
        const newSet = new Set(prev);
        processedIds.forEach((id) => newSet.add(id));
        return newSet;
      });
      
      // Показываем сообщение об успехе
      const actionLabels = {
        restore: 'возвращены в OrcaSlicer',
        delete: 'убран из "Профили филамента"',
        skip: 'обработаны',
      };
      const currentAction = action; // Сохраняем action до сброса
      const actionLabel = currentAction ? actionLabels[currentAction] || 'обработаны' : 'обработаны';
      const count = processedIds.length;
      setSuccessMessage(`${count} ${count === 1 ? 'пресет' : count < 5 ? 'пресета' : 'пресетов'} ${actionLabel}`);
      
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
          console.error('Ошибка при удалении уведомления:', error);
        }
      }
    },
    onError: (error: any) => {
      console.error('Ошибка при обработке действия:', error);
      const errorMessage = error?.response?.data?.detail || error?.message || 'Неизвестная ошибка';
      alert(`Ошибка при обработке действия: ${errorMessage}`);
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
      console.warn('Действие не выбрано');
      return;
    }

    if (selectedPresetIds.size === 0) {
      console.warn('Не выбраны пресеты');
      alert('Пожалуйста, выберите хотя бы один пресет');
      return;
    }

    const presetIds = Array.from(selectedPresetIds);
    const applyToAll = presetIds.length === deletedPresets.length;

    console.log('Применяю действие:', {
      action,
      presetIds,
      applyToAll,
      saveRule,
    });

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
        console.error('Ошибка при автоматической обработке пресетов:', error);
      }
    }
    
    onClose();
  };

  const getActionButton = (actionType: 'restore' | 'delete' | 'skip') => {
    const configs = {
      restore: {
        icon: <RotateCcw className="w-4 h-4" />,
        label: 'Вернуть в OrcaSlicer',
        bg: 'bg-blue-600 hover:bg-blue-700',
        shortDescription: 'Пресет появится в OrcaSlicer снова',
        fullDescription: 'Пресет вернётся в OrcaSlicer при следующей синхронизации. Останется доступен в FilamentHub.',
      },
      delete: {
        icon: <Trash2 className="w-4 h-4" />,
        label: 'Убрать из "Профили филамента"',
        bg: 'bg-red-600 hover:bg-red-700',
        shortDescription: 'Пресет исчезнет из вашего профиля',
        fullDescription: 'Пресет будет убран из раздела "Профили филамента". Останется доступен в каталоге FilamentHub. Пресеты, созданные вами, не удаляются.',
      },
      skip: {
        icon: <SkipForward className="w-4 h-4" />,
        label: 'Оставить как есть',
        bg: 'bg-gray-600 hover:bg-gray-700',
        shortDescription: 'Ничего не делать с пресетом',
        fullDescription: 'Пресет останется в FilamentHub, но больше не будет синхронизироваться с OrcaSlicer.',
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

  return createPortal(
    <div
      className={`fixed inset-0 bg-black/50 backdrop-blur-sm z-50 overflow-y-auto ${
        isHeaderVisible ? 'pt-[88px]' : ''
      }`}
      onClick={(e) => {
        if (e.target === e.currentTarget && !handleActionMutation.isPending) {
          handleCloseWithAutoSkip();
        }
      }}
    >
      <div className="min-h-full flex items-center justify-center p-4">
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
                <h3 className="text-xl font-bold text-white">Пресеты удалены в OrcaSlicer</h3>
                <p className="text-sm text-gray-400 mt-1">
                  Вы удалили {deletedPresets.length} {deletedPresets.length === 1 ? 'пресет' : deletedPresets.length < 5 ? 'пресета' : 'пресетов'} в OrcaSlicer. 
                  Выберите, что сделать с ними в FilamentHub.
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
                <span className="text-gray-300">Всего пресетов:</span>
                <span className="text-white font-semibold">{deletedPresets.length}</span>
              </div>
              {createdCount > 0 && (
                <div className="flex items-center justify-between text-sm mt-1">
                  <span className="text-gray-300">Созданных пользователем:</span>
                  <span className="text-blue-400 font-semibold">{createdCount}</span>
                </div>
              )}
              {savedCount > 0 && (
                <div className="flex items-center justify-between text-sm mt-1">
                  <span className="text-gray-300">Сохранённых из каталога:</span>
                  <span className="text-green-400 font-semibold">{savedCount}</span>
                </div>
              )}
            </div>

            {/* Presets List */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-semibold text-white">Выберите пресеты:</h4>
                {deletedPresets.length > 0 && (
                  <button
                    onClick={handleSelectAll}
                    className="text-sm text-purple-400 hover:text-purple-300 transition-colors"
                  >
                    {Array.from(deletedPresets.map((p) => p.preset_id)).every((id) => selectedPresetIds.has(id))
                      ? 'Снять выделение'
                      : 'Выбрать все'}
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
                              Создан
                            </span>
                          )}
                          {preset.is_saved && (
                            <span className="px-1.5 py-0.5 bg-green-500/20 text-green-400 text-xs rounded flex-shrink-0">
                              Сохранён
                            </span>
                          )}
                        </div>
                        {preset.bundle_preset_name && (
                          <p className="text-xs text-gray-400 mt-1 break-words">
                            OrcaSlicer: {preset.bundle_preset_name}
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
              <h4 className="text-sm font-semibold text-white mb-3">Что сделать с выбранными пресетами?</h4>
              <div className="grid grid-cols-3 gap-3">
                {getActionButton('restore')}
                {getActionButton('delete')}
                {getActionButton('skip')}
              </div>
              {action && (
                <div className="mt-3 p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                  <p className="text-sm text-blue-300 font-medium mb-1">
                    {action === 'restore' && 'Вернуть в OrcaSlicer'}
                    {action === 'delete' && 'Убрать из "Профили филамента"'}
                    {action === 'skip' && 'Оставить как есть'}
                  </p>
                  <p className="text-xs text-blue-200/80">
                    {action === 'restore' && 'Пресет вернётся в OrcaSlicer при следующей синхронизации. Останется доступен в FilamentHub.'}
                    {action === 'delete' && 'Пресет будет убран из раздела "Профили филамента" на сайте. Останется доступен в каталоге FilamentHub. ⚠️ Пресеты, созданные вами, не удаляются.'}
                    {action === 'skip' && 'Пресет останется в FilamentHub, но больше не будет автоматически синхронизироваться с OrcaSlicer.'}
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
                    Сохранить это действие как правило для будущих удалений
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
              Закрыть
            </button>
            <button
              onClick={handleApplyAction}
              disabled={!action || selectedPresetIds.size === 0 || handleActionMutation.isPending}
              className="px-6 py-2.5 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
            >
              {handleActionMutation.isPending ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Выполнение...</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Применить</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};



