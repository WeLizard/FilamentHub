/** Компонент для управления режимом технических работ */

import { useState, useEffect } from 'react';
import { Settings, AlertTriangle, CheckCircle, Loader2 } from 'lucide-react';
import { api } from '../../api/client';

interface MaintenanceInfo {
  enabled: boolean;
  message: string | null;
}

export function AdminMaintenance() {
  const [maintenanceInfo, setMaintenanceInfo] = useState<MaintenanceInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isUpdating, setIsUpdating] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Загружаем текущий статус
  useEffect(() => {
    loadMaintenanceStatus();
  }, []);

  const loadMaintenanceStatus = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await api.get('/admin/maintenance');
      setMaintenanceInfo(response.data);
      setMessage(response.data.message || '');
    } catch (err: any) {
      console.error('Failed to load maintenance status:', err);
      setError(err.response?.data?.detail || 'Не удалось загрузить статус технических работ');
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleMaintenance = async (enabled: boolean) => {
    if (!confirm(
      enabled
        ? 'Включить режим технических работ? Сайт станет недоступен для всех пользователей (кроме админов).'
        : 'Выключить режим технических работ? Сайт снова станет доступен для всех пользователей.'
    )) {
      return;
    }

    try {
      setIsUpdating(true);
      setError(null);
      const response = await api.post('/admin/maintenance', {
        enabled,
        message: message.trim() || null,
      });
      setMaintenanceInfo(response.data.maintenance_mode);
      setMessage(response.data.maintenance_mode.message || '');
    } catch (err: any) {
      console.error('Failed to update maintenance mode:', err);
      setError(err.response?.data?.detail || 'Не удалось обновить режим технических работ');
    } finally {
      setIsUpdating(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-purple-400" />
        <span className="ml-3 text-gray-300">Загрузка статуса...</span>
      </div>
    );
  }

  const isEnabled = maintenanceInfo?.enabled || false;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-6">
        <Settings className="w-6 h-6 text-purple-400" />
        <h2 className="text-2xl font-bold text-white">Технические работы</h2>
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4">
          <div className="flex items-center gap-2 text-red-300">
            <AlertTriangle className="w-5 h-5" />
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* Текущий статус */}
      <div className={`rounded-xl p-6 border-2 ${
        isEnabled
          ? 'bg-yellow-900/20 border-yellow-500/30'
          : 'bg-green-900/20 border-green-500/30'
      }`}>
        <div className="flex items-center gap-3 mb-4">
          {isEnabled ? (
            <>
              <AlertTriangle className="w-6 h-6 text-yellow-400" />
              <h3 className="text-xl font-semibold text-yellow-300">Режим технических работ ВКЛЮЧЕН</h3>
            </>
          ) : (
            <>
              <CheckCircle className="w-6 h-6 text-green-400" />
              <h3 className="text-xl font-semibold text-green-300">Режим технических работ ВЫКЛЮЧЕН</h3>
            </>
          )}
        </div>

        {isEnabled && maintenanceInfo?.message && (
          <div className="mt-4 p-4 bg-yellow-900/30 rounded-lg border border-yellow-500/20">
            <p className="text-yellow-200 text-sm font-medium mb-1">Сообщение для пользователей:</p>
            <p className="text-yellow-100">{maintenanceInfo.message}</p>
          </div>
        )}

        <div className="mt-4 text-sm text-gray-300">
          {isEnabled ? (
            <p>
              Сайт временно недоступен для всех пользователей. 
              Доступ к админ-панели и API для управления режимом сохранен.
            </p>
          ) : (
            <p>Сайт доступен для всех пользователей.</p>
          )}
        </div>
      </div>

      {/* Управление */}
      <div className="bg-white/5 rounded-xl p-6 border border-white/10">
        <h3 className="text-lg font-semibold text-white mb-4">Управление режимом</h3>

        {/* Сообщение */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Сообщение для пользователей (опционально)
          </label>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Например: Ведутся технические работы. Ожидаемое время восстановления: 1 час."
            className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
            rows={3}
          />
          <p className="mt-1 text-xs text-gray-400">
            Если не указано, будет использовано стандартное сообщение
          </p>
        </div>

        {/* Кнопки */}
        <div className="flex gap-3">
          <button
            onClick={() => handleToggleMaintenance(true)}
            disabled={isUpdating || isEnabled}
            className={`
              flex items-center gap-2 px-6 py-3 rounded-lg font-semibold transition-all
              ${isEnabled
                ? 'bg-gray-600/30 text-gray-400 cursor-not-allowed'
                : 'bg-yellow-600 hover:bg-yellow-700 text-white'
              }
            `}
          >
            {isUpdating ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                <span>Обновление...</span>
              </>
            ) : (
              <>
                <AlertTriangle className="w-5 h-5" />
                <span>Включить технические работы</span>
              </>
            )}
          </button>

          <button
            onClick={() => handleToggleMaintenance(false)}
            disabled={isUpdating || !isEnabled}
            className={`
              flex items-center gap-2 px-6 py-3 rounded-lg font-semibold transition-all
              ${!isEnabled
                ? 'bg-gray-600/30 text-gray-400 cursor-not-allowed'
                : 'bg-green-600 hover:bg-green-700 text-white'
              }
            `}
          >
            {isUpdating ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                <span>Обновление...</span>
              </>
            ) : (
              <>
                <CheckCircle className="w-5 h-5" />
                <span>Выключить технические работы</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Информация */}
      <div className="bg-blue-900/20 border border-blue-500/30 rounded-xl p-4">
        <h4 className="text-sm font-semibold text-blue-300 mb-2">Как это работает:</h4>
        <ul className="text-sm text-blue-200 space-y-1 list-disc list-inside">
          <li>При включении режима все запросы к API (кроме /health и /api/v1/admin/maintenance) возвращают ошибку 503</li>
          <li>Фронтенд должен обрабатывать ошибку 503 и показывать сообщение о технических работах</li>
          <li>Администраторы могут войти в систему и управлять режимом через админ-панель</li>
          <li>Режим хранится в памяти сервера (при перезапуске сбрасывается)</li>
        </ul>
      </div>
    </div>
  );
}

