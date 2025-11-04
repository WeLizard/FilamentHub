/** Компонент для модерации пресетов */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Settings, CheckCircle, XCircle } from 'lucide-react';
import { adminAPI } from '../../api/client';
import type { Preset } from '../../types/api';

export function AdminPresets() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);

  // Загрузка пресетов ожидающих модерации
  const { data: pendingPresets, isLoading } = useQuery({
    queryKey: ['admin-pending-presets', page],
    queryFn: () => adminAPI.listPendingPresets({ page, size: 20 }),
  });

  // Одобрение пресета
  const approveMutation = useMutation({
    mutationFn: (presetId: number) => adminAPI.approvePreset(presetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-pending-presets'] });
    },
  });

  // Отклонение пресета
  const rejectMutation = useMutation({
    mutationFn: ({ presetId, reason }: { presetId: number; reason: string }) =>
      adminAPI.rejectPreset(presetId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-pending-presets'] });
    },
  });

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">Загрузка пресетов...</div>;
  }

  const presets = pendingPresets || [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-2">Модерация пресетов</h2>
        <p className="text-gray-400">Ожидающие модерации: {presets.length}</p>
      </div>

      {presets.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Settings className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>Нет пресетов, ожидающих модерации</p>
        </div>
      ) : (
        <div className="space-y-4">
          {presets.map((preset) => (
            <div
              key={preset.id}
              className="bg-white/5 rounded-xl p-4 border border-white/10 hover:border-white/20 transition-all"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    <Settings className="w-5 h-5 text-purple-400" />
                    <h3 className="text-lg font-semibold text-white">{preset.name}</h3>
                  </div>
                  {preset.description && (
                    <p className="text-sm text-gray-400 mb-2">{preset.description}</p>
                  )}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm text-gray-400">
                    <div>Сопло: {preset.extruder_temp}°C</div>
                    <div>Стол: {preset.bed_temp}°C</div>
                    <div>Скорость: {preset.print_speed}mm/s</div>
                    <div>Использований: {preset.usage_count}</div>
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    Создан: {new Date(preset.created_at).toLocaleString('ru-RU')}
                  </p>
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => {
                      if (confirm(`Одобрить пресет "${preset.name}"?`)) {
                        approveMutation.mutate(preset.id);
                      }
                    }}
                    disabled={approveMutation.isPending}
                    className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-all disabled:opacity-50"
                  >
                    <CheckCircle className="w-4 h-4" />
                    <span>Одобрить</span>
                  </button>
                  <button
                    onClick={() => {
                      const reason = prompt('Укажите причину отклонения:');
                      if (reason && reason.trim()) {
                        rejectMutation.mutate({ presetId: preset.id, reason: reason.trim() });
                      }
                    }}
                    disabled={rejectMutation.isPending}
                    className="flex items-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-all disabled:opacity-50"
                  >
                    <XCircle className="w-4 h-4" />
                    <span>Отклонить</span>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

