/** Поле выбора типа материала: ввод + выпадающий список существующих типов
 *  (typeahead). Общий контрол для формы филамента и палитры. */

import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { sortMaterialTypes } from '../data/materialDefaults';

const FALLBACK_TYPES = ['PLA', 'PETG', 'ABS', 'TPU', 'ASA', 'PC', 'PA', 'PVA'];

interface MaterialTypeSelectProps {
  value: string;
  onChange: (value: string) => void;
  /** Срабатывает только при явном выборе пункта из списка (не при ручном вводе). */
  onSelect?: (value: string) => void;
  options: string[];
  label?: string;
  placeholder?: string;
  required?: boolean;
}

export function MaterialTypeSelect({ value, onChange, onSelect, options, label, placeholder, required }: MaterialTypeSelectProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Популярные материалы — вперёд (как было в исходном селекторе), затем по алфавиту.
  const allTypes = sortMaterialTypes(options.length > 0 ? options : FALLBACK_TYPES);
  const query = value.toLowerCase();
  const isExact = allTypes.some((type) => type.toLowerCase() === query);
  const filtered = isExact ? allTypes : allTypes.filter((type) => type.toLowerCase().includes(query));

  return (
    <div className="relative" ref={ref}>
      {label && <label className="block text-gray-300 mb-2 text-sm font-medium">{label}</label>}
      <input
        type="text"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder={placeholder ?? t('createFilament.selectOrEnterMaterial')}
        required={required}
        className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
      />
      {open && (
        <div
          className="absolute z-10 w-full mt-1 max-h-60 overflow-y-auto bg-white/5 backdrop-blur-sm rounded-xl border border-white/10 shadow-xl"
          onClick={(e) => e.stopPropagation()}
        >
          {filtered.length > 0 ? (
            filtered.map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => {
                  onChange(type);
                  onSelect?.(type);
                  setOpen(false);
                }}
                className="w-full px-4 py-3 text-left hover:bg-white/10 transition-all text-white border-b border-white/5 last:border-b-0"
              >
                {type}
              </button>
            ))
          ) : (
            <div className="px-4 py-3 text-gray-400 text-sm">{t('createFilament.noTypesFound')}</div>
          )}
        </div>
      )}
    </div>
  );
}
