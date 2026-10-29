import type { TFunction } from 'i18next';
import type { FilamentTechnicalProperty } from '../types/api';

export type TechnicalCategory = 'mechanical' | 'thermal' | 'physical' | 'electrical' | 'optical';

/** Display order and grouping; mirrors backend app/services/technical_properties.py. */
export const TECHNICAL_PROPERTY_CATEGORIES: Record<string, TechnicalCategory> = {
  tensile_strength: 'mechanical',
  tensile_modulus: 'mechanical',
  elongation: 'mechanical',
  flexural_strength: 'mechanical',
  flexural_modulus: 'mechanical',
  compressive_strength: 'mechanical',
  impact_charpy: 'mechanical',
  impact_izod: 'mechanical',
  shore_hardness: 'mechanical',
  hdt: 'thermal',
  vicat: 'thermal',
  melting_temperature: 'thermal',
  glass_transition: 'thermal',
  service_temperature_max: 'thermal',
  melt_flow_rate: 'physical',
  melt_volume_rate: 'physical',
  shrinkage: 'physical',
  water_absorption: 'physical',
  diameter_tolerance: 'physical',
  ovality: 'physical',
  surface_resistivity: 'electrical',
  light_transmission: 'optical',
};

export const TECHNICAL_CATEGORY_ORDER: TechnicalCategory[] = ['mechanical', 'thermal', 'physical', 'electrical', 'optical'];

const NUMERIC_CONDITIONS = new Set(['load_mpa', 'load_n', 'load_kg', 'temperature_c', 'rate_c_per_h']);

/** Same identity as the server's technical_property_key: addresses one measurement's evidence. */
export const technicalPropertyKey = (item: Pick<FilamentTechnicalProperty, 'code' | 'conditions' | 'standard'>): string => {
  const conditions = item.conditions ?? {};
  const parts = [item.code, ...Object.keys(conditions).sort().map(name => `${name}=${conditions[name]}`)];
  const standard = (item.standard ?? '').split(/\s+/).filter(Boolean).join(' ');
  if (standard) parts.push(`std=${standard}`);
  return parts.join(';');
};

/** "52 ± 3 MPa", "190–220 °C", "95 Shore A" in the reader's locale. */
export const formatTechnicalValue = (item: FilamentTechnicalProperty, locale: string): string => {
  const number = (value: number) => new Intl.NumberFormat(locale, { maximumFractionDigits: 3 }).format(value);
  const amount = item.value != null
    ? `${number(item.value)}${item.tolerance != null ? ` ± ${number(item.tolerance)}` : ''}`
    : `${number(item.min ?? 0)}–${number(item.max ?? 0)}`;
  const scale = item.code === 'shore_hardness' ? item.conditions?.scale : undefined;
  return `${amount} ${item.unit}${scale ? ` ${scale}` : ''}`;
};

/** Test conditions as short readable phrases ("XY", "0.45 MPa", "notched"). */
export const technicalConditions = (item: FilamentTechnicalProperty, t: TFunction, locale: string): string[] =>
  Object.entries(item.conditions ?? {})
    .filter(([name]) => !(item.code === 'shore_hardness' && name === 'scale'))
    .map(([name, value]) => NUMERIC_CONDITIONS.has(name)
      ? t(`technicalProperties.conditions.${name}`, {
        value: new Intl.NumberFormat(locale, { maximumFractionDigits: 3 }).format(Number(value)),
      })
      : t(`technicalProperties.conditionValues.${name}.${value}`, { defaultValue: String(value) }));

export const sortTechnicalProperties = (items: FilamentTechnicalProperty[]): FilamentTechnicalProperty[] => {
  const order = Object.keys(TECHNICAL_PROPERTY_CATEGORIES);
  return [...items].sort((left, right) => {
    const leftIndex = order.indexOf(left.code);
    const rightIndex = order.indexOf(right.code);
    return (leftIndex === -1 ? order.length : leftIndex) - (rightIndex === -1 ? order.length : rightIndex);
  });
};
