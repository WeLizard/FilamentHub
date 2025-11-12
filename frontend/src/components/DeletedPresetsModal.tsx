/** Модалка для обработки удалённых пресетов */

import { useState } from 'react';
import { createPortal } from 'react-dom';
import { X, RotateCcw, Trash2, SkipForward, CheckCircle2 } from 'lucide-react';
import { useHeaderVisible } from '../hooks/useHeaderVisible';
import { orcaslicerDeletedPresetsAPI } from '../api/client';
import { useMutation, useQueryClient } from '@tanstack/react-query';
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
  notification,
}) => {
  const isHeaderVisible = useHeaderVisible();
  const queryClient = useQueryClient();
  const [selectedPresetIds, setSelectedPresetIds] = useState<Set<number>>(new Set());
  const [action, setAction] = useState<'restore' | 'delete' | 'skip' | null>(null);
  const [saveRule, setSaveRule] = useState(false);

  if (!isOpen || !notification.extra_data) return null;

  const deletedPresets: DeletedPreset[] = notification.extra_data.deleted_presets || [];
  const createdCount = notification.extra_data.created_count || 0;
  const savedCount = notification.extra_data.saved_count || 0;

  // Инициализируем выбранные пресеты (все по умолчанию)
  if (selectedPresetIds.size === 0 && deletedPresets.length > 0) {
    setSelectedPresetIds(new Set(deletedPresets.map((p) => p.preset_id)));
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
    if (selectedPresetIds.size === deletedPresets.length) {
      setSelectedPresetIds(new Set());
    } else {
      setSelectedPresetIds(new Set(deletedPresets.map((p) => p.preset_id)));
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
      onClose();
    },
  });

  const handleApplyAction = () => {
    if (!action) return;

    const presetIds = Array.from(selectedPresetIds);
    const applyToAll = presetIds.length === deletedPresets.length;

    handleActionMutation.mutate({
      action,
      preset_ids: applyToAll ? null : presetIds,
      apply_to_all: applyToAll,
      save_rule: saveRule,
    });
  };

  const getActionButton = (actionType: 'restore' | 'delete' | 'skip') => {
    const configs = {
      restore: {
        icon: <RotateCcw className="w-4 h-4" />,
        label: 'Восстановить',
        bg: 'bg-blue-600 hover:bg-blue-700',
        description: 'Восстановить пресеты в OrcaSlicer при следующей синхронизации',
      },
      delete: {
        icon: <Trash2 className="w-4 h-4" />,
        label: 'Удалить',
        bg: 'bg-red-600 hover:bg-red-700',
        description: 'Удалить сохранённые пресеты из "Мои пресеты" (созданные не удаляются)',
      },
      skip: {
        icon: <SkipForward className="w-4 h-4" />,
        label: 'Пропустить',
        bg: 'bg-gray-600 hover:bg-gray-700',
        description: 'Пропустить обработку (удалить маппинг)',
      },
    };

    const config = configs[actionType];
    const isSelected = action === actionType;

    return (
      <button
        onClick={() => setAction(actionType)}
        className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-all ${
          isSelected
            ? `${config.bg} text-white border-2 border-white/50`
            : 'bg-white/10 hover:bg-white/20 text-gray-300 border-2 border-transparent'
        }`}
      >
        {config.icon}
        <span className="font-medium">{config.label}</span>
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
          onClose();
        }
      }}
    >
      <div className="min-h-full flex items-center justify-center p-4">
        <div
          className="bg-gradient-to-br from-purple-900 to-indigo-900 rounded-2xl max-w-2xl w-full overflow-hidden flex flex-col border border-white/20 shadow-xl"
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
                <h3 className="text-xl font-bold text-white">{notification.title}</h3>
                <p className="text-sm text-gray-400 mt-1">{notification.message}</p>
              </div>
            </div>
            <button
              onClick={onClose}
              disabled={handleActionMutation.isPending}
              className="text-gray-400 hover:text-white transition-colors disabled:opacity-50"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <div className="p-6 overflow-y-auto flex-1 max-h-[60vh]">
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
                <button
                  onClick={handleSelectAll}
                  className="text-sm text-purple-400 hover:text-purple-300 transition-colors"
                >
                  {selectedPresetIds.size === deletedPresets.length ? 'Снять выделение' : 'Выбрать все'}
                </button>
              </div>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {deletedPresets.map((preset) => {
                  const isSelected = selectedPresetIds.has(preset.preset_id);
                  return (
                    <label
                      key={preset.preset_id}
                      className={`flex items-start space-x-3 p-3 rounded-lg cursor-pointer transition-all ${
                        isSelected ? 'bg-purple-500/20 border border-purple-500/50' : 'bg-white/5 hover:bg-white/10'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => handleTogglePreset(preset.preset_id)}
                        className="mt-1 w-4 h-4 rounded border-gray-400 text-purple-600 focus:ring-purple-500"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center space-x-2">
                          <span className="text-sm font-medium text-white">{preset.preset_name}</span>
                          {preset.is_created && (
                            <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 text-xs rounded">
                              Создан
                            </span>
                          )}
                          {preset.is_saved && (
                            <span className="px-2 py-0.5 bg-green-500/20 text-green-400 text-xs rounded">
                              Сохранён
                            </span>
                          )}
                        </div>
                        {preset.bundle_preset_name && (
                          <p className="text-xs text-gray-400 mt-1">
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
              <h4 className="text-sm font-semibold text-white mb-3">Выберите действие:</h4>
              <div className="flex flex-wrap gap-3">
                {getActionButton('restore')}
                {getActionButton('delete')}
                {getActionButton('skip')}
              </div>
              {action && (
                <p className="text-xs text-gray-400 mt-2">
                  {action === 'restore' && 'Восстановить пресеты в OrcaSlicer при следующей синхронизации'}
                  {action === 'delete' && 'Удалить сохранённые пресеты из "Мои пресеты" (созданные не удаляются)'}
                  {action === 'skip' && 'Пропустить обработку (удалить маппинг)'}
                </p>
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
              onClick={onClose}
              disabled={handleActionMutation.isPending}
              className="px-6 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Отмена
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



