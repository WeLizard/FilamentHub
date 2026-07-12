/** Поле плотности (г/см³). Авто-подставляется из материала родителем.
 *  `locked` — для обычного юзера на известном материале плотность нельзя править;
 *  производитель (`locked=false`) знает свою реальную плотность и правит. */

import { useTranslation } from 'react-i18next';

import { InfoHint } from './InfoHint';

interface DensityFieldProps {
  value: number;
  onChange: (value: number) => void;
  locked?: boolean;
  label?: string;
}

export function DensityField({ value, onChange, locked = false, label }: DensityFieldProps) {
  const { t } = useTranslation();
  return (
    <div>
      <label className="block text-gray-300 mb-2 text-sm font-medium">{label ?? t('createFilament.densityLabel')} <InfoHint text={t('paramHints.density')} /></label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={locked}
        min={0.1}
        max={25}
        step="0.01"
        className={`w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all ${locked ? 'opacity-60 cursor-not-allowed' : ''}`}
        placeholder="1.24"
      />
      {locked && <p className="text-gray-500 text-xs mt-1">{t('createFilament.densityLockedHint')}</p>}
    </div>
  );
}
