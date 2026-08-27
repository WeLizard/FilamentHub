import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { RecommendedPresetItem } from '../types/api';
import type { PrinterConfigurationOption } from '../hooks/useConfigurationPresetRecommendation';

interface PrinterConfigurationSelectProps {
  options: PrinterConfigurationOption[];
  selectedKey: string;
  onChange: (key: string) => void;
  isLoading?: boolean;
  isError?: boolean;
  compact?: boolean;
}

export function PrinterConfigurationSelect({
  options,
  selectedKey,
  onChange,
  isLoading = false,
  isError = false,
  compact = false,
}: PrinterConfigurationSelectProps) {
  const { t } = useTranslation();

  return (
    <label className="block min-w-0">
      <span className="mb-1 flex items-center gap-2 text-xs font-medium text-slate-300">
        {t('myPrinters.configurations')}
        {isLoading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      </span>
      <select
        value={selectedKey}
        onChange={(event) => onChange(event.target.value)}
        disabled={isLoading}
        className={`w-full rounded-lg border border-white/15 bg-slate-900 text-slate-100 outline-none transition focus:border-purple-400/60 disabled:opacity-60 ${
          compact ? 'px-2.5 py-1.5 text-xs' : 'px-3 py-2 text-sm'
        }`}
      >
        <option value="">{t('filamentDetailPage.anyPrinter')}</option>
        {options.map((option) => (
          <option key={option.key} value={option.key}>
            {option.label}
          </option>
        ))}
      </select>
      {!isLoading && options.length === 0 && !isError && (
        <span className="mt-1 block text-xs text-slate-500">
          {t('myPrinters.noConfigurations')}
        </span>
      )}
      {isError && (
        <span className="mt-1 block text-xs text-amber-300/80">
          {t('myPrinters.loadError')}
        </span>
      )}
    </label>
  );
}

const compatibilityTone = {
  compatible: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-200',
  incompatible: 'border-red-400/25 bg-red-400/10 text-red-200',
  unknown: 'border-amber-400/25 bg-amber-400/10 text-amber-200',
};

interface PresetRecommendationEvidenceProps {
  recommendation: RecommendedPresetItem;
  printerName: string;
}

export function PresetRecommendationEvidence({
  recommendation,
  printerName,
}: PresetRecommendationEvidenceProps) {
  const { t } = useTranslation();

  return (
    <div className="mt-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-slate-400">
          {t('profilePage.calculator.printerCompatibilityTitle', { name: printerName })}
        </span>
        <span className={`rounded-full border px-2 py-0.5 ${compatibilityTone[recommendation.compatibility_status]}`}>
          {t(`profilePage.calculator.printerCompatibilityStatus.${recommendation.compatibility_status}`)}
        </span>
      </div>
      {recommendation.compatibility_checks.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-slate-400">
          {recommendation.compatibility_checks.map((check) => (
            <span key={check.kind} className={check.status === 'incompatible' ? 'text-red-300' : undefined}>
              {t(`profilePage.calculator.printerCompatibilityKind.${check.kind}`)}:{' '}
              {check.available_value == null
                ? t('profilePage.calculator.printerCompatibilityUnknownValue')
                : t('profilePage.calculator.printerCompatibilityValues', {
                    required: `${check.required_value}${check.unit}`,
                    available: `${check.available_value}${check.unit}`,
                  })}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
