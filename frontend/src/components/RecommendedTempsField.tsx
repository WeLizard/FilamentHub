import React from 'react';
import { useTranslation } from 'react-i18next';

export interface RecommendedTemps {
  nozzleMin: number | null;
  nozzleMax: number | null;
  bedMin: number | null;
  bedMax: number | null;
}

export const EMPTY_RECOMMENDED_TEMPS: RecommendedTemps = {
  nozzleMin: null,
  nozzleMax: null,
  bedMin: null,
  bedMax: null,
};

const inputClass =
  'min-w-0 w-full px-3 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all disabled:cursor-not-allowed disabled:opacity-60';

const parseNum = (raw: string): number | null => (raw === '' ? null : Number(raw));

/**
 * Vendor-set recommended print temperature ranges (material spec).
 * A range, not concrete profile values — presets pull it as a starting default.
 */
export const RecommendedTempsField: React.FC<{
  value: RecommendedTemps;
  onChange: (value: RecommendedTemps) => void;
  disabled?: Partial<Record<keyof RecommendedTemps, boolean>>;
}> = ({ value, onChange, disabled = {} }) => {
  const { t } = useTranslation();
  const temperatureInput = (
    key: keyof RecommendedTemps,
    label: string,
    example: number,
  ) => (
    <label className="grid min-w-0 grid-cols-[4.25rem_minmax(4.5rem,1fr)] items-center gap-1.5">
      <span className="text-xs leading-tight text-gray-400">{label}</span>
      <input
        type="number"
        min={0}
        placeholder={t('createFilament.temperatureExample', { value: example })}
        value={value[key] ?? ''}
        disabled={disabled[key]}
        onChange={(event) => onChange({ ...value, [key]: parseNum(event.target.value) })}
        className={inputClass}
      />
    </label>
  );

  return (
    <div>
      <label className="block text-gray-300 mb-1 text-sm font-medium">
        {t('createFilament.recommendedTempsLabel')}
      </label>
      <p className="text-gray-400 text-xs mb-2">{t('createFilament.recommendedTempsHint')}</p>
      <div className="grid gap-x-4 gap-y-2 md:grid-cols-2">
        <div className="space-y-2">
          {temperatureInput('nozzleMin', t('createFilament.nozzleTempMin'), 200)}
          {temperatureInput('nozzleMax', t('createFilament.nozzleTempMax'), 230)}
        </div>
        <div className="space-y-2">
          {temperatureInput('bedMin', t('createFilament.bedTempMin'), 50)}
          {temperatureInput('bedMax', t('createFilament.bedTempMax'), 70)}
        </div>
      </div>
    </div>
  );
};
