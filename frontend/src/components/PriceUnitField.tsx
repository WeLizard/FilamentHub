/** Переключатель «цена за кг / за катушку» + цена + вес катушки. Общий контрол
 *  для формы филамента и палитры — чтобы UX был одинаковым. */

import { useTranslation } from 'react-i18next';

interface PriceUnitFieldProps {
  priceMode: 'per_kg' | 'per_spool';
  onPriceModeChange: (mode: 'per_kg' | 'per_spool') => void;
  pricePerKg: number;
  onPricePerKgChange: (value: number) => void;
  pricePerSpool: number;
  onPricePerSpoolChange: (value: number) => void;
  spoolWeight: number;
  onSpoolWeightChange: (value: number) => void;
  emptySpoolWeight: number | null;
  onEmptySpoolWeightChange: (value: number | null) => void;
  currencySymbol: string;
}

export function PriceUnitField({
  priceMode,
  onPriceModeChange,
  pricePerKg,
  onPricePerKgChange,
  pricePerSpool,
  onPricePerSpoolChange,
  spoolWeight,
  onSpoolWeightChange,
  emptySpoolWeight,
  onEmptySpoolWeightChange,
  currencySymbol,
}: PriceUnitFieldProps) {
  const { t } = useTranslation();

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-gray-300 text-sm font-medium">
            {priceMode === 'per_kg'
              ? t('createFilament.pricePerKgLabel', { currency: currencySymbol })
              : t('createFilament.pricePerSpoolLabel', { currency: currencySymbol })}
          </label>
          <div className="flex items-center bg-white/10 rounded-lg p-1 border border-white/20">
            <button
              type="button"
              onClick={() => onPriceModeChange('per_kg')}
              className={`px-2 py-1 text-xs rounded transition-all ${priceMode === 'per_kg' ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'}`}
              title={t('createFilament.pricePerKg')}
            >
              {t('createFilament.pricePerKg')}
            </button>
            <button
              type="button"
              onClick={() => onPriceModeChange('per_spool')}
              className={`px-2 py-1 text-xs rounded transition-all ${priceMode === 'per_spool' ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'}`}
              title={t('createFilament.pricePerSpool')}
            >
              {t('createFilament.pricePerSpool')}
            </button>
          </div>
        </div>
        <input
          type="number"
          value={priceMode === 'per_kg' ? (pricePerKg || '') : (pricePerSpool || '')}
          onChange={(e) => {
            const value = e.target.value === '' ? 0 : Number(e.target.value);
            if (priceMode === 'per_kg') onPricePerKgChange(value);
            else onPricePerSpoolChange(value);
          }}
          min={0}
          step="0.01"
          className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
          placeholder="800"
        />
        {priceMode === 'per_kg' && pricePerKg > 0 && spoolWeight > 0 && (
          <p className="text-xs text-gray-400 mt-1">
            ≈ {((pricePerKg * spoolWeight) / 1000).toFixed(2)} {t('createFilament.rubPerSpool', { currency: currencySymbol })}
          </p>
        )}
        {priceMode === 'per_spool' && pricePerSpool > 0 && spoolWeight > 0 && (
          <p className="text-xs text-gray-400 mt-1">
            ≈ {((pricePerSpool / spoolWeight) * 1000).toFixed(2)} {t('createFilament.rubPerKg', { currency: currencySymbol })}
          </p>
        )}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col">
          <div className="h-[34px] mb-2 flex items-end">
            <label className="block text-gray-300 text-sm font-medium">{t('createFilament.spoolWeightLabel')}</label>
          </div>
          <input
            type="number"
            value={spoolWeight || ''}
            onChange={(e) => onSpoolWeightChange(e.target.value === '' ? 0 : Number(e.target.value))}
            min={0}
            step="1"
            className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
            placeholder="1000"
          />
        </div>
        <div className="flex flex-col">
          <div className="h-[34px] mb-2 flex items-end">
            <label className="block text-gray-300 text-sm font-medium">{t('createFilament.emptySpoolWeightLabel')}</label>
          </div>
          <input
            type="number"
            value={emptySpoolWeight ?? ''}
            onChange={(e) => onEmptySpoolWeightChange(e.target.value === '' ? null : Number(e.target.value))}
            min={0}
            step="1"
            className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
            placeholder={t('createFilament.emptySpoolWeightPlaceholder')}
          />
        </div>
      </div>
    </div>
  );
}
