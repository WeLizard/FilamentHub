import { Package } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { FilamentPackaging } from '../types/api';
import { formatNetWeight, packagingKey, packagingWeightLabel } from '../utils/packaging';

interface FilamentPackagingsProps {
  packagings: FilamentPackaging[];
  className?: string;
}

/** Every size and carrier the manufacturer sells this filament in. */
export function FilamentPackagings({ packagings, className = '' }: FilamentPackagingsProps) {
  const { t, i18n } = useTranslation();
  if (packagings.length === 0) return null;
  const locale = i18n.language;
  const number = (value: number) => new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value);

  const details = (item: FilamentPackaging): string[] => {
    const lines: string[] = [];
    if (item.empty_spool_weight_g != null && item.package_type !== 'refill' && item.package_type !== 'coil') {
      lines.push(t('filamentPackaging.emptySpool', { weight: formatNetWeight(item.empty_spool_weight_g, t, locale) }));
    }
    if (item.spool_outer_diameter_mm != null || item.spool_width_mm != null) {
      lines.push(
        [
          item.spool_outer_diameter_mm != null ? `Ø ${number(item.spool_outer_diameter_mm)}` : null,
          item.spool_width_mm != null ? number(item.spool_width_mm) : null,
        ].filter(Boolean).join(' × ') + ` ${t('catalogPage.units.mm')}`,
      );
    }
    if (item.spool_core_diameter_mm != null) {
      lines.push(t('filamentPackaging.core', { value: number(item.spool_core_diameter_mm) }));
    }
    if (item.gross_weight_g != null) {
      lines.push(t('filamentPackaging.gross', { weight: formatNetWeight(item.gross_weight_g, t, locale) }));
    }
    if (item.sku) lines.push(t('filamentPackaging.sku', { code: item.sku }));
    if (item.ean) lines.push(`EAN ${item.ean}`);
    return lines;
  };

  const carrier = (item: FilamentPackaging): string => {
    const type = item.package_type ?? 'spool';
    return type === 'spool' && item.spool_material && item.spool_material !== 'none'
      ? t(`filamentPackaging.spoolMaterial.${item.spool_material}`)
      : t(`filamentPackaging.type.${type}`);
  };

  return (
    <section
      aria-labelledby="filament-packagings-title"
      className={`rounded-xl border border-white/10 bg-white/5 p-3 md:p-4 ${className}`}
    >
      <h2 id="filament-packagings-title" className="mb-2 flex items-center gap-2 text-sm font-semibold text-white">
        <Package className="h-4 w-4 text-blue-400" />
        {t('filamentPackaging.title')}
      </h2>
      <ul className="flex flex-wrap gap-2">
        {packagings.map(item => (
          <li
            key={packagingKey(item)}
            className="min-w-[7.5rem] rounded-lg border border-white/10 bg-black/15 px-3 py-2"
          >
            <div className="text-base font-semibold text-white">{packagingWeightLabel(item, t, locale)}</div>
            <div className="text-xs text-gray-300">{carrier(item)}</div>
            {details(item).map(line => (
              <div key={line} className="text-[11px] leading-4 text-gray-400">{line}</div>
            ))}
          </li>
        ))}
      </ul>
    </section>
  );
}
