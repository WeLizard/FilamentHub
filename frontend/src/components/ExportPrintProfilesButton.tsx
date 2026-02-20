/** Кнопка экспорта print profiles из OrcaSlicer в FilamentHub */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Upload, Loader2, CheckCircle, AlertCircle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

interface ExportPrintProfilesButtonProps {
  onExportComplete?: (result: { success: boolean; message?: string }) => void;
}

export const ExportPrintProfilesButton: React.FC<ExportPrintProfilesButtonProps> = ({ onExportComplete }) => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [isExporting, setIsExporting] = useState(false);
  const [exportStatus, setExportStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [statusMessage, setStatusMessage] = useState<string>('');
  const [isInOrcaSlicer, setIsInOrcaSlicer] = useState(false);
  const isExportDisabled = user?.allow_print_profiles_export === false;

  // Проверяем, запущен ли frontend внутри OrcaSlicer
  useEffect(() => {
    const checkOrcaSlicer = () => {
      const inOrca = typeof window !== 'undefined' && (
        (window as any).filamenthub?.exportPrintProfiles ||
        (window as any).wx?.postMessage
      );
      setIsInOrcaSlicer(inOrca || false);
    };

    checkOrcaSlicer();

    // Периодически проверяем наличие API (на случай, если оно загружается асинхронно)
    const interval = setInterval(checkOrcaSlicer, 1000);
    return () => clearInterval(interval);
  }, []);

  // Обработчик экспорта print profiles
  const handleExport = async () => {
    if (isExporting || !isInOrcaSlicer) {
      return;
    }

    setIsExporting(true);
    setExportStatus('idle');
    setStatusMessage('');

    try {
      // Проверяем наличие API
      if (!(window as any).filamenthub?.exportPrintProfiles) {
        throw new Error('OrcaSlicer API is not available.');
      }

      // Вызываем экспорт через JavaScript API
      const result = await (window as any).filamenthub.exportPrintProfiles();
      
      setExportStatus('success');

      // Вызываем callback, если передан
      if (onExportComplete) {
        onExportComplete({ success: true, message: result.message });
      }

      // Сбрасываем статус через 3 секунды
      setTimeout(() => {
        setExportStatus('idle');
      }, 3000);
    } catch (error: any) {
      console.error('Print profiles export error:', error);

      setExportStatus('error');
      setStatusMessage(error.message || t('exportPrintProfiles.exportError'));
      
      // Вызываем callback, если передан
      if (onExportComplete) {
        onExportComplete({ success: false, message: error.message });
      }

      // Сбрасываем статус через 5 секунд
      setTimeout(() => {
        setExportStatus('idle');
        setStatusMessage('');
      }, 5000);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="flex flex-col gap-1">
      <button
        onClick={handleExport}
        disabled={isExporting || !isInOrcaSlicer || isExportDisabled}
        className={`
          px-3 py-1.5 rounded-lg border text-xs font-medium transition-all
          ${isExporting || !isInOrcaSlicer || isExportDisabled
            ? 'bg-white/5 border-white/10 text-gray-400 cursor-not-allowed opacity-50'
            : exportStatus === 'success'
            ? 'bg-green-500/20 border-green-500/40 text-green-400 hover:bg-green-500/30'
            : exportStatus === 'error'
            ? 'bg-red-500/20 border-red-500/40 text-red-400 hover:bg-red-500/30'
            : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10 hover:text-white'
          }
        `}
        title={
          isExportDisabled
            ? t('exportPrintProfiles.disabled')
            : !isInOrcaSlicer
            ? t('exportPrintProfiles.onlyInOrca')
            : t('exportPrintProfiles.title')
        }
      >
        {isExporting ? (
          <>
            <Loader2 className="w-3 h-3 inline mr-1.5 animate-spin" />
            {t('exportPrintProfiles.exporting')}
          </>
        ) : exportStatus === 'success' ? (
          <>
            <CheckCircle className="w-3 h-3 inline mr-1.5" />
            {t('exportPrintProfiles.done')}
          </>
        ) : exportStatus === 'error' ? (
          <>
            <AlertCircle className="w-3 h-3 inline mr-1.5" />
            {t('exportPrintProfiles.error')}
          </>
        ) : (
          <>
            <Upload className="w-3 h-3 inline mr-1.5" />
            {t('exportPrintProfiles.button')}
          </>
        )}
      </button>
      
      {/* Сообщение о статусе */}
      {statusMessage && (
        <p className={`text-xs ${
          exportStatus === 'success' ? 'text-green-400' :
          exportStatus === 'error' ? 'text-red-400' :
          'text-gray-400'
        }`}>
          {statusMessage}
        </p>
      )}
    </div>
  );
};

