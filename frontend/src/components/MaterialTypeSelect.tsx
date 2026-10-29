/** Поле выбора типа материала: ввод + выпадающий список, сгруппированный по
 *  семейству (PLA, PETG, PA…). Общий контрол для формы филамента, палитры и пресета. */

import { useState, useRef, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { filamentsAPI } from '../api/client';
import { sortMaterialTypes } from '../data/materialDefaults';
import {
  filterMaterialTypeGroups,
  materialBaseLabel,
  mergeMaterialTypes,
} from '../utils/materialTypeGroups';

export const FALLBACK_TYPES = ['PLA', 'PETG', 'ABS', 'TPU', 'ASA', 'PC', 'PA', 'PVA'];

interface MaterialTypeSelectProps {
  value: string;
  onChange: (value: string) => void;
  /** Срабатывает только при явном выборе пункта из списка (не при ручном вводе). */
  onSelect?: (value: string) => void;
  /** Типы, которые форма уже знает; добавляются к справочнику, ничего не скрывая. */
  options: string[];
  label?: string;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  /** Accessible name when there is no visible label. */
  ariaLabel?: string;
  /** sm: compact field for dense admin forms. */
  size?: 'sm' | 'md';
}

export function MaterialTypeSelect({
  value, onChange, onSelect, options, label, placeholder, required, disabled, ariaLabel, size = 'md',
}: MaterialTypeSelectProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const { data: groups } = useQuery({
    queryKey: ['filaments', 'material-types', 'groups'],
    queryFn: () => filamentsAPI.getMaterialTypeGroups(),
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const allGroups = useMemo(() => {
    if (groups && groups.length > 0) return mergeMaterialTypes(groups, options);
    // До ответа сервера — плоский список, как раньше.
    const flat = sortMaterialTypes(options.length > 0 ? options : FALLBACK_TYPES);
    return [{ base: '', types: flat, filament_count: 0 }];
  }, [groups, options]);

  const label_ = (base: string | null) => materialBaseLabel(t, base);
  const visible = filterMaterialTypeGroups(allGroups, value, label_);

  const choose = (type: string) => {
    onChange(type);
    onSelect?.(type);
    setOpen(false);
  };

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
        onBlur={() => setOpen(false)}
        placeholder={placeholder ?? t('createFilament.selectOrEnterMaterial')}
        required={required}
        disabled={disabled}
        aria-label={ariaLabel}
        className={`w-full border text-white placeholder-gray-400 focus:outline-none transition-all disabled:opacity-60 ${size === 'sm'
          ? 'h-9 rounded-lg border-white/15 bg-slate-950/70 px-2.5 text-sm focus:border-indigo-400'
          : 'px-4 py-3 bg-white/10 border-white/20 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent'}`}
      />
      {open && (
        <div
          className="scrollbar-contained absolute z-50 w-full mt-1 max-h-72 overflow-y-auto rounded-xl border border-white/20 bg-gray-800/90 shadow-xl backdrop-blur-md"
          onClick={(e) => e.stopPropagation()}
        >
          {visible.length > 0 ? (
            visible.map((group) => (
              <div key={group.base ?? 'other'} role="group" aria-label={group.base === '' ? undefined : label_(group.base)}>
                {group.base !== '' && (
                  <div className="sticky top-0 z-[1] flex items-baseline justify-between gap-3 border-b border-white/5 bg-gray-800/95 px-4 pt-2 pb-1 text-[11px] uppercase tracking-wide text-gray-400">
                    <span>{label_(group.base)}</span>
                    {group.filament_count > 0 && (
                      <span className="normal-case tracking-normal text-gray-500">
                        {t('materialTypes.familyCount', { count: group.filament_count })}
                      </span>
                    )}
                  </div>
                )}
                {group.types.map((type) => (
                  <button
                    key={type}
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => choose(type)}
                    className={`w-full px-4 py-2.5 text-left transition-colors border-b border-white/5 last:border-b-0 hover:bg-white/10 ${
                      type.toLowerCase() === value.trim().toLowerCase() ? 'text-purple-300' : 'text-white'
                    }`}
                  >
                    {type}
                  </button>
                ))}
              </div>
            ))
          ) : (
            <div className="px-4 py-3 text-gray-400 text-sm">{t('createFilament.noTypesFound')}</div>
          )}
        </div>
      )}
    </div>
  );
}
