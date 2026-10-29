import type { TFunction } from 'i18next';
import type { FilamentPackaging } from '../types/api';

/** 750 → "750 г", 2500 → "2,5 кг" in the reader's locale. */
export const formatNetWeight = (grams: number, t: TFunction, locale: string): string => {
  if (grams >= 1000) {
    const kilograms = new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(grams / 1000);
    return `${kilograms} ${t('catalogPage.units.kg')}`;
  }
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(grams)} ${t('catalogPage.units.g')}`;
};

/** "4 × 1 кг" for a multipack, otherwise the net weight. */
export const packagingWeightLabel = (item: FilamentPackaging, t: TFunction, locale: string): string => {
  const weight = formatNetWeight(item.net_weight_g, t, locale);
  return item.package_type === 'multipack' && item.units_per_package
    ? `${item.units_per_package} × ${weight}`
    : weight;
};

/** Net weights a buyer can pick when adding a spool, main packaging first. */
export const singleSpoolWeights = (packagings: FilamentPackaging[] | undefined): number[] => [
  ...new Set((packagings ?? []).map(item => item.net_weight_g)),
];

/** Same identity as the server's packaging_key: addresses one packaging's evidence. */
export const packagingKey = (item: Pick<FilamentPackaging, 'net_weight_g' | 'package_type' | 'units_per_package'>): string => {
  const weight = String(Number(Number(item.net_weight_g || 0).toPrecision(6)));
  return `${item.package_type || 'spool'}:${weight}${item.units_per_package ? `x${item.units_per_package}` : ''}`;
};
