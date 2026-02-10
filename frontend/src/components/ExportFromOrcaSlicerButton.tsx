/** Кнопка экспорта filament presets из OrcaSlicer в FilamentHub */

import { useState, useEffect } from 'react';
import { Upload, Loader2, CheckCircle, AlertCircle } from 'lucide-react';

interface ExportFromOrcaSlicerButtonProps {
  onExportComplete?: (result: { success: boolean; message?: string }) => void;
}

export const ExportFromOrcaSlicerButton: React.FC<ExportFromOrcaSlicerButtonProps> = ({ onExportComplete }) => {
  const [isExporting, setIsExporting] = useState(false);
  const [exportStatus, setExportStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [statusMessage, setStatusMessage] = useState<string>('');
  const [isInOrcaSlicer, setIsInOrcaSlicer] = useState(false);

  // Проверяем, запущен ли frontend внутри OrcaSlicer
  useEffect(() => {
    const checkOrcaSlicer = () => {
      const inOrca = typeof window !== 'undefined' && (
        (window as any).filamenthub?.exportFilamentPresets ||
        (window as any).wx?.postMessage
      );
      setIsInOrcaSlicer(inOrca || false);
    };

    checkOrcaSlicer();

    // Периодически проверяем наличие API (на случай, если оно загружается асинхронно)
    const interval = setInterval(checkOrcaSlicer, 1000);
    return () => clearInterval(interval);
  }, []);

  // Обработчик экспорта filament presets
  const handleExport = async () => {
    if (isExporting || !isInOrcaSlicer) {
      return;
    }

    setIsExporting(true);
    setExportStatus('idle');
    setStatusMessage('');

    try {
      // Проверяем наличие API
      if (!(window as any).filamenthub?.exportFilamentPresets) {
        throw new Error('OrcaSlicer API не доступно. Убедитесь, что вы используете FilamentHub внутри OrcaSlicer.');
      }

      // Вызываем экспорт через JavaScript API
      const result = await (window as any).filamenthub.exportFilamentPresets();
      
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
      console.error('Ошибка экспорта filament presets:', error);
      
      setExportStatus('error');
      setStatusMessage(error.message || 'Ошибка при экспорте профилей. Проверьте логи для деталей.');
      
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

  // Если не в OrcaSlicer, не показываем кнопку
  if (!isInOrcaSlicer) {
    return null;
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={handleExport}
        disabled={isExporting}
        className={`
          px-4 py-2 rounded-lg border text-sm font-medium transition-all
          ${isExporting
            ? 'bg-white/10 border-white/20 text-gray-400 cursor-not-allowed'
            : exportStatus === 'success'
            ? 'bg-green-500/20 border-green-500/50 text-green-400 hover:bg-green-500/30'
            : exportStatus === 'error'
            ? 'bg-red-500/20 border-red-500/50 text-red-400 hover:bg-red-500/30'
            : 'bg-white/10 border-white/20 text-white hover:bg-white/20'
          }
        `}
        title="Экспортировать filament presets из OrcaSlicer в FilamentHub"
      >
        {isExporting ? (
          <>
            <Loader2 className="w-4 h-4 inline mr-2 animate-spin" />
            Экспорт...
          </>
        ) : exportStatus === 'success' ? (
          <>
            <CheckCircle className="w-4 h-4 inline mr-2" />
            Экспорт начат
          </>
        ) : exportStatus === 'error' ? (
          <>
            <AlertCircle className="w-4 h-4 inline mr-2" />
            Ошибка
          </>
        ) : (
          <>
            <Upload className="w-4 h-4 inline mr-2" />
            Экспортировать из OrcaSlicer
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




