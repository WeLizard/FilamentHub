/** Цена и её единица: «за кг» или «за катушку». Общий контрол для формы
 *  филамента и страновой ячейки — единица цены везде выбирается одинаково. */

import { useTranslation } from 'react-i18next';

interface PriceWithUnitProps {
  priceMode: 'per_kg' | 'per_spool';
  onPriceModeChange: (mode: 'per_kg' | 'per_spool') => void;
  value: number;
  onValueChange: (value: number) => void;
  currencySymbol: string;
  /** Пересчёт в другую единицу показывается, только когда вес катушки известен. */
  spoolWeight?: number;
  disabled?: boolean;
}

export function PriceWithUnit({
  priceMode,
  onPriceModeChange,
  value,
  onValueChange,
  currencySymbol,
  spoolWeight = 0,
  disabled = false,
}: PriceWithUnitProps) {
  const { t } = useTranslation();

  return (
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
            disabled={disabled}
            onClick={() => onPriceModeChange('per_kg')}
            className={`px-2 py-1 text-xs rounded transition-all disabled:cursor-not-allowed disabled:opacity-60 ${priceMode === 'per_kg' ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'}`}
            title={t('createFilament.pricePerKg')}
          >
            {t('createFilament.pricePerKg')}
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onPriceModeChange('per_spool')}
            className={`px-2 py-1 text-xs rounded transition-all disabled:cursor-not-allowed disabled:opacity-60 ${priceMode === 'per_spool' ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'}`}
            title={t('createFilament.pricePerSpool')}
          >
            {t('createFilament.pricePerSpool')}
          </button>
        </div>
      </div>
      <input
        type="number"
        disabled={disabled}
        value={value || ''}
        onChange={(e) => onValueChange(e.target.value === '' ? 0 : Number(e.target.value))}
        min={0}
        step="0.01"
        className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all disabled:cursor-not-allowed disabled:opacity-60"
        placeholder="800"
      />
      {priceMode === 'per_kg' && value > 0 && spoolWeight > 0 && (
        <p className="text-xs text-gray-400 mt-1">
          ≈ {((value * spoolWeight) / 1000).toFixed(2)}{' '}
          {t('createFilament.rubPerSpool', { currency: currencySymbol })}
        </p>
      )}
      {priceMode === 'per_spool' && value > 0 && spoolWeight > 0 && (
        <p className="text-xs text-gray-400 mt-1">
          ≈ {((value / spoolWeight) * 1000).toFixed(2)}{' '}
          {t('createFilament.rubPerKg', { currency: currencySymbol })}
        </p>
      )}
    </div>
  );
}
