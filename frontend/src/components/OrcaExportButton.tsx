import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertCircle, CheckCircle, Loader2, Upload } from 'lucide-react';

import {
  useOrcaBridgeCapability,
  type OrcaBridgeCapability,
} from '../hooks/useOrcaBridgeCapability';
import { isPluginEmbed, requestPluginProfileSync } from '../utils/pluginBridge';

export interface OrcaExportResult {
  success: boolean;
  message?: string;
}

interface OrcaExportButtonProps {
  capability: OrcaBridgeCapability;
  translationPrefix: 'exportOrcaSlicer' | 'exportPrinterProfiles' | 'exportPrintProfiles';
  successLabel: 'started' | 'done';
  onExportComplete?: (result: OrcaExportResult) => void;
  disabled?: boolean;
  hideWhenUnavailable?: boolean;
  size?: 'compact' | 'regular';
  errorContext: string;
}

type ExportStatus = 'idle' | 'success' | 'error';

const compactClasses = {
  wrapper: 'flex flex-col gap-1',
  button: 'px-3 py-1.5 rounded-lg border text-xs font-medium transition-all',
  disabled: 'bg-white/5 border-white/10 text-gray-400 cursor-not-allowed opacity-50',
  idle: 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10 hover:text-white',
  success: 'bg-green-500/20 border-green-500/40 text-green-400 hover:bg-green-500/30',
  error: 'bg-red-500/20 border-red-500/40 text-red-400 hover:bg-red-500/30',
  icon: 'w-3 h-3 inline mr-1.5',
};

const regularClasses = {
  wrapper: 'flex flex-col gap-2',
  button: 'px-4 py-2 rounded-lg border text-sm font-medium transition-all',
  disabled: 'bg-white/10 border-white/20 text-gray-400 cursor-not-allowed',
  idle: 'bg-white/10 border-white/20 text-white hover:bg-white/20',
  success: 'bg-green-500/20 border-green-500/50 text-green-400 hover:bg-green-500/30',
  error: 'bg-red-500/20 border-red-500/50 text-red-400 hover:bg-red-500/30',
  icon: 'w-4 h-4 inline mr-2',
};

const errorMessage = (error: unknown): string | undefined => (
  error instanceof Error ? error.message : undefined
);

export function OrcaExportButton({
  capability,
  translationPrefix,
  successLabel,
  onExportComplete,
  disabled = false,
  hideWhenUnavailable = false,
  size = 'compact',
  errorContext,
}: OrcaExportButtonProps) {
  const { t } = useTranslation();
  const available = useOrcaBridgeCapability(capability);
  const [isExporting, setIsExporting] = useState(false);
  const [status, setStatus] = useState<ExportStatus>('idle');
  const [statusMessage, setStatusMessage] = useState('');
  const resetTimerRef = useRef<number | null>(null);
  const inFlightRef = useRef(false);
  const mountedRef = useRef(true);
  const classes = size === 'regular' ? regularClasses : compactClasses;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (resetTimerRef.current !== null) window.clearTimeout(resetTimerRef.current);
    };
  }, []);

  const scheduleReset = (delay: number) => {
    if (resetTimerRef.current !== null) window.clearTimeout(resetTimerRef.current);
    resetTimerRef.current = window.setTimeout(() => {
      setStatus('idle');
      setStatusMessage('');
      resetTimerRef.current = null;
    }, delay);
  };

  const handleExport = async () => {
    if (inFlightRef.current || !available || disabled) return;

    const legacyExporter = window.filamenthub?.[capability];
    if (!legacyExporter && !isPluginEmbed()) {
      setStatus('error');
      setStatusMessage(t(`${translationPrefix}.exportError`));
      scheduleReset(5000);
      return;
    }

    inFlightRef.current = true;
    setIsExporting(true);
    setStatus('idle');
    setStatusMessage('');

    try {
      const result = legacyExporter
        ? await legacyExporter()
        : await requestPluginProfileSync();
      if (!mountedRef.current) return;
      setStatus('success');
      onExportComplete?.({ success: true, message: result.message });
      scheduleReset(3000);
    } catch (error: unknown) {
      console.error(`${errorContext} export error:`, error);
      if (!mountedRef.current) return;
      const message = errorMessage(error);
      setStatus('error');
      setStatusMessage(message || t(`${translationPrefix}.exportError`));
      onExportComplete?.({ success: false, message });
      scheduleReset(5000);
    } finally {
      inFlightRef.current = false;
      if (mountedRef.current) setIsExporting(false);
    }
  };

  if (hideWhenUnavailable && !available) return null;

  const isDisabled = isExporting || !available || disabled;
  const toneClass = isDisabled
    ? classes.disabled
    : status === 'success'
      ? classes.success
      : status === 'error'
        ? classes.error
        : classes.idle;
  const title = disabled
    ? t(`${translationPrefix}.disabled`)
    : !available
      ? t(`${translationPrefix}.onlyInOrca`)
      : t(`${translationPrefix}.title`);

  return (
    <div className={classes.wrapper}>
      <button
        type="button"
        onClick={() => void handleExport()}
        disabled={isDisabled}
        className={`${classes.button} ${toneClass}`}
        title={title}
      >
        {isExporting ? (
          <><Loader2 className={`${classes.icon} animate-spin`} />{t(`${translationPrefix}.exporting`)}</>
        ) : status === 'success' ? (
          <><CheckCircle className={classes.icon} />{t(`${translationPrefix}.${successLabel}`)}</>
        ) : status === 'error' ? (
          <><AlertCircle className={classes.icon} />{t(`${translationPrefix}.error`)}</>
        ) : (
          <><Upload className={classes.icon} />{t(`${translationPrefix}.button`)}</>
        )}
      </button>

      {statusMessage && (
        <p className={`text-xs ${status === 'error' ? 'text-red-400' : 'text-gray-400'}`}>
          {statusMessage}
        </p>
      )}
    </div>
  );
}
