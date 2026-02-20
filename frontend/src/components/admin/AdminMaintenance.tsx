/** Компонент для управления режимом технических работ */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Settings, AlertTriangle, CheckCircle, Loader2 } from 'lucide-react';
import api from '../../api/client';

interface MaintenanceInfo {
  enabled: boolean;
  message: string | null;
}

export function AdminMaintenance() {
  const { t } = useTranslation();
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
      setError(err.response?.data?.detail || t('adminMaintenance.loadError'));
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleMaintenance = async (enabled: boolean) => {
    if (!confirm(
      enabled
        ? t('adminMaintenance.confirmEnable')
        : t('adminMaintenance.confirmDisable')
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
      setError(err.response?.data?.detail || t('adminMaintenance.updateError'));
    } finally {
      setIsUpdating(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-purple-400" />
        <span className="ml-3 text-gray-300">{t('adminMaintenance.loadingStatus')}</span>
      </div>
    );
  }

  const isEnabled = maintenanceInfo?.enabled || false;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-6">
        <Settings className="w-6 h-6 text-purple-400" />
        <h2 className="text-2xl font-bold text-white">{t('adminMaintenance.title')}</h2>
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
              <h3 className="text-xl font-semibold text-yellow-300">{t('adminMaintenance.statusEnabled')}</h3>
            </>
          ) : (
            <>
              <CheckCircle className="w-6 h-6 text-green-400" />
              <h3 className="text-xl font-semibold text-green-300">{t('adminMaintenance.statusDisabled')}</h3>
            </>
          )}
        </div>

        {isEnabled && maintenanceInfo?.message && (
          <div className="mt-4 p-4 bg-yellow-900/30 rounded-lg border border-yellow-500/20">
            <p className="text-yellow-200 text-sm font-medium mb-1">{t('adminMaintenance.userMessage')}:</p>
            <p className="text-yellow-100">{maintenanceInfo.message}</p>
          </div>
        )}

        <div className="mt-4 text-sm text-gray-300">
          {isEnabled ? (
            <p>{t('adminMaintenance.siteUnavailable')}</p>
          ) : (
            <p>{t('adminMaintenance.siteAvailable')}</p>
          )}
        </div>
      </div>

      {/* Управление */}
      <div className="bg-white/5 rounded-xl p-6 border border-white/10">
        <h3 className="text-lg font-semibold text-white mb-4">{t('adminMaintenance.modeControl')}</h3>

        {/* Сообщение */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            {t('adminMaintenance.messageLabel')}
          </label>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={t('adminMaintenance.messagePlaceholder')}
            className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
            rows={3}
          />
          <p className="mt-1 text-xs text-gray-400">
            {t('adminMaintenance.messageHint')}
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
                <span>{t('adminMaintenance.updating')}</span>
              </>
            ) : (
              <>
                <AlertTriangle className="w-5 h-5" />
                <span>{t('adminMaintenance.enableBtn')}</span>
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
                <span>{t('adminMaintenance.updating')}</span>
              </>
            ) : (
              <>
                <CheckCircle className="w-5 h-5" />
                <span>{t('adminMaintenance.disableBtn')}</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Информация */}
      <div className="bg-blue-900/20 border border-blue-500/30 rounded-xl p-4">
        <h4 className="text-sm font-semibold text-blue-300 mb-2">{t('adminMaintenance.howItWorks')}</h4>
        <ul className="text-sm text-blue-200 space-y-1 list-disc list-inside">
          <li>{t('adminMaintenance.info1')}</li>
          <li>{t('adminMaintenance.info2')}</li>
          <li>{t('adminMaintenance.info3')}</li>
          <li>{t('adminMaintenance.info4')}</li>
        </ul>
      </div>
    </div>
  );
}

