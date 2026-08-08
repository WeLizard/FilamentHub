/** Переключатель «цена за кг / за катушку» + цена + вес катушки. Общий контрол
 *  для формы филамента и палитры — чтобы UX был одинаковым. */

import { useTranslation } from 'react-i18next';

import { PriceWithUnit } from './PriceWithUnit';

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
  /** Цену задаёт рынок: у страновой организации она живёт в её ячейке. */
  showPrice?: boolean;
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
  showPrice = true,
}: PriceUnitFieldProps) {
  const { t } = useTranslation();

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {showPrice && (
      <PriceWithUnit
        priceMode={priceMode}
        onPriceModeChange={onPriceModeChange}
        value={priceMode === 'per_kg' ? pricePerKg : pricePerSpool}
        onValueChange={priceMode === 'per_kg' ? onPricePerKgChange : onPricePerSpoolChange}
        currencySymbol={currencySymbol}
        spoolWeight={spoolWeight}
      />
      )}
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
