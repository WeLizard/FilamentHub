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
  'w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all';

const parseNum = (raw: string): number | null => (raw === '' ? null : Number(raw));

/**
 * Vendor-set recommended print temperature ranges (material spec).
 * A range, not concrete profile values — presets pull it as a starting default.
 */
export const RecommendedTempsField: React.FC<{
  value: RecommendedTemps;
  onChange: (value: RecommendedTemps) => void;
}> = ({ value, onChange }) => {
  const { t } = useTranslation();
  return (
    <div>
      <label className="block text-gray-300 mb-1 text-sm font-medium">
        {t('createFilament.recommendedTempsLabel')}
      </label>
      <p className="text-gray-400 text-xs mb-2">{t('createFilament.recommendedTempsHint')}</p>
      <div className="grid grid-cols-2 gap-3">
        <input
          type="number"
          min={0}
          value={value.nozzleMin ?? ''}
          onChange={(e) => onChange({ ...value, nozzleMin: parseNum(e.target.value) })}
          placeholder={t('createFilament.nozzleTempMin')}
          className={inputClass}
        />
        <input
          type="number"
          min={0}
          value={value.nozzleMax ?? ''}
          onChange={(e) => onChange({ ...value, nozzleMax: parseNum(e.target.value) })}
          placeholder={t('createFilament.nozzleTempMax')}
          className={inputClass}
        />
        <input
          type="number"
          min={0}
          value={value.bedMin ?? ''}
          onChange={(e) => onChange({ ...value, bedMin: parseNum(e.target.value) })}
          placeholder={t('createFilament.bedTempMin')}
          className={inputClass}
        />
        <input
          type="number"
          min={0}
          value={value.bedMax ?? ''}
          onChange={(e) => onChange({ ...value, bedMax: parseNum(e.target.value) })}
          placeholder={t('createFilament.bedTempMax')}
          className={inputClass}
        />
      </div>
    </div>
  );
};
