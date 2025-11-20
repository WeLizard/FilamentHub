/** Кнопка экспорта printer profiles из OrcaSlicer в FilamentHub */

import { useState, useEffect } from 'react';
import { Upload, Loader2, CheckCircle, AlertCircle } from 'lucide-react';

interface ExportPrinterProfilesButtonProps {
  onExportComplete?: (result: { success: boolean; message?: string }) => void;
}

export const ExportPrinterProfilesButton: React.FC<ExportPrinterProfilesButtonProps> = ({ onExportComplete }) => {
  const [isExporting, setIsExporting] = useState(false);
  const [exportStatus, setExportStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [statusMessage, setStatusMessage] = useState<string>('');
  const [isInOrcaSlicer, setIsInOrcaSlicer] = useState(false);

  // Проверяем, запущен ли frontend внутри OrcaSlicer
  useEffect(() => {
    const checkOrcaSlicer = () => {
      const inOrca = typeof window !== 'undefined' && (
        (window as any).filamenthub?.exportPrinterProfiles ||
        (window as any).wx?.postMessage
      );
      setIsInOrcaSlicer(inOrca || false);
    };

    checkOrcaSlicer();

    // Периодически проверяем наличие API (на случай, если оно загружается асинхронно)
    const interval = setInterval(checkOrcaSlicer, 1000);
    return () => clearInterval(interval);
  }, []);

  // Обработчик экспорта printer profiles
  const handleExport = async () => {
    if (isExporting || !isInOrcaSlicer) {
      return;
    }

    setIsExporting(true);
    setExportStatus('idle');
    setStatusMessage('');

    try {
      // Проверяем наличие API
      if (!(window as any).filamenthub?.exportPrinterProfiles) {
        throw new Error('OrcaSlicer API не доступно. Убедитесь, что вы используете FilamentHub внутри OrcaSlicer.');
      }

      // Вызываем экспорт через JavaScript API
      const result = await (window as any).filamenthub.exportPrinterProfiles();
      
      setExportStatus('success');
      setStatusMessage(result.message || 'Экспорт начат. Результат будет показан в уведомлениях.');
      
      // Вызываем callback, если передан
      if (onExportComplete) {
        onExportComplete({ success: true, message: result.message });
      }

      // Сбрасываем статус через 3 секунды
      setTimeout(() => {
        setExportStatus('idle');
        setStatusMessage('');
      }, 3000);
    } catch (error: any) {
      console.error('Ошибка экспорта printer profiles:', error);
      
      setExportStatus('error');
      setStatusMessage(error.message || 'Ошибка при экспорте профилей принтера. Проверьте логи для деталей.');
      
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
        disabled={isExporting || !isInOrcaSlicer}
        className={`
          px-3 py-1.5 rounded-lg border text-xs font-medium transition-all
          ${isExporting || !isInOrcaSlicer
            ? 'bg-white/5 border-white/10 text-gray-400 cursor-not-allowed opacity-50'
            : exportStatus === 'success'
            ? 'bg-green-500/20 border-green-500/40 text-green-400 hover:bg-green-500/30'
            : exportStatus === 'error'
            ? 'bg-red-500/20 border-red-500/40 text-red-400 hover:bg-red-500/30'
            : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10 hover:text-white'
          }
        `}
        title={
          !isInOrcaSlicer
            ? "Экспорт доступен только внутри OrcaSlicer"
            : "Экспортировать printer profiles из OrcaSlicer в FilamentHub"
        }
      >
        {isExporting ? (
          <>
            <Loader2 className="w-3 h-3 inline mr-1.5 animate-spin" />
            Экспорт...
          </>
        ) : exportStatus === 'success' ? (
          <>
            <CheckCircle className="w-3 h-3 inline mr-1.5" />
            Готово
          </>
        ) : exportStatus === 'error' ? (
          <>
            <AlertCircle className="w-3 h-3 inline mr-1.5" />
            Ошибка
          </>
        ) : (
          <>
            <Upload className="w-3 h-3 inline mr-1.5" />
            Из OrcaSlicer
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

