import { Plus, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { FilamentPackaging } from '../types/api';

type PackageType = NonNullable<FilamentPackaging['package_type']>;
type SpoolMaterial = NonNullable<FilamentPackaging['spool_material']>;

const PACKAGE_TYPES: PackageType[] = ['spool', 'refill', 'coil', 'multipack'];
const SPOOL_MATERIALS: SpoolMaterial[] = ['plastic', 'cardboard', 'metal'];
const SPOOLLESS = new Set<PackageType>(['refill', 'coil']);

interface FilamentPackagingsEditorProps {
  value: FilamentPackaging[];
  onChange: (value: FilamentPackaging[]) => void;
  disabled?: boolean;
}

const fieldCls = 'rounded-lg border border-white/15 bg-white/10 px-2.5 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-60';

const numberOrNull = (raw: string): number | null => {
  const parsed = Number(raw.replace(',', '.'));
  return raw.trim() === '' || !Number.isFinite(parsed) ? null : parsed;
};

/**
 * Every size the manufacturer sells. Dimensions, SKU and EAN arrive with
 * catalog intake and are kept as they are.
 */
export function FilamentPackagingsEditor({ value, onChange, disabled = false }: FilamentPackagingsEditorProps) {
  const { t } = useTranslation();

  const update = (index: number, changes: Partial<FilamentPackaging>) => {
    onChange(value.map((item, position) => {
      if (position !== index) return item;
      const next = { ...item, ...changes };
      const type = next.package_type ?? 'spool';
      if (type !== 'multipack') next.units_per_package = null;
      else if (!next.units_per_package) next.units_per_package = 2;
      if (SPOOLLESS.has(type)) {
        next.spool_material = null;
        next.empty_spool_weight_g = null;
        next.spool_outer_diameter_mm = null;
        next.spool_width_mm = null;
        next.spool_core_diameter_mm = null;
      }
      return next;
    }));
  };

  return (
    <div>
      <div className="mb-1.5 text-sm font-medium text-gray-300">{t('filamentPackaging.title')}</div>
      <p className="mb-2 text-xs text-gray-400">{t('filamentPackaging.editorHint')}</p>
      <ul className="space-y-2">
        {value.map((item, index) => {
          const type = item.package_type ?? 'spool';
          return (
            <li key={index} className="flex flex-wrap items-center gap-2">
              <label className="inline-flex items-center gap-1.5 text-xs text-gray-400">
                <input
                  type="text"
                  inputMode="decimal"
                  aria-label={t('filamentPackaging.netWeight')}
                  value={item.net_weight_g || ''}
                  disabled={disabled}
                  onChange={(event) => update(index, { net_weight_g: numberOrNull(event.target.value) ?? 0 })}
                  className={`${fieldCls} w-24`}
                />
                {t('catalogPage.units.g')}
              </label>
              <select
                aria-label={t('filamentPackaging.packageType')}
                value={type}
                disabled={disabled}
                onChange={(event) => update(index, { package_type: event.target.value as PackageType })}
                className={`${fieldCls} w-44 bg-slate-900`}
              >
                {PACKAGE_TYPES.map(option => (
                  <option key={option} value={option}>{t(`filamentPackaging.type.${option}`)}</option>
                ))}
              </select>
              {type === 'multipack' && (
                <label className="inline-flex items-center gap-1.5 text-xs text-gray-400">
                  ×
                  <input
                    type="number"
                    min={2}
                    max={100}
                    aria-label={t('filamentPackaging.units')}
                    value={item.units_per_package ?? 2}
                    disabled={disabled}
                    onChange={(event) => update(index, { units_per_package: Math.max(2, Number(event.target.value) || 2) })}
                    className={`${fieldCls} w-16`}
                  />
                </label>
              )}
              {!SPOOLLESS.has(type) && (
                <>
                  <select
                    aria-label={t('filamentPackaging.spoolMaterialLabel')}
                    value={item.spool_material ?? ''}
                    disabled={disabled}
                    onChange={(event) => update(index, { spool_material: (event.target.value || null) as SpoolMaterial | null })}
                    className={`${fieldCls} w-48 bg-slate-900`}
                  >
                    <option value="">{t('filamentPackaging.spoolMaterialUnknown')}</option>
                    {SPOOL_MATERIALS.map(option => (
                      <option key={option} value={option}>{t(`filamentPackaging.spoolMaterial.${option}`)}</option>
                    ))}
                  </select>
                  <label className="inline-flex items-center gap-1.5 text-xs text-gray-400">
                    {t('filamentPackaging.emptySpoolShort')}
                    <input
                      type="text"
                      inputMode="decimal"
                      value={item.empty_spool_weight_g ?? ''}
                      disabled={disabled}
                      onChange={(event) => update(index, { empty_spool_weight_g: numberOrNull(event.target.value) })}
                      className={`${fieldCls} w-20`}
                    />
                    {t('catalogPage.units.g')}
                  </label>
                </>
              )}
              <button
                type="button"
                disabled={disabled}
                onClick={() => onChange(value.filter((_, position) => position !== index))}
                aria-label={t('filamentPackaging.remove')}
                className="rounded-lg p-1.5 text-gray-400 transition hover:bg-white/10 hover:text-white disabled:opacity-40"
              >
                <X className="h-4 w-4" />
              </button>
            </li>
          );
        })}
      </ul>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange([...value, { net_weight_g: 0, package_type: 'spool' }])}
        className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/5 px-2.5 py-1.5 text-sm text-gray-200 transition hover:bg-white/10 disabled:opacity-40"
      >
        <Plus className="h-4 w-4" />
        {t('filamentPackaging.add')}
      </button>
    </div>
  );
}
