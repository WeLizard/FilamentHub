import type { TFunction } from 'i18next';
import type { MaterialTypeGroup } from '../types/api';

/** `material_base` value for materials whose polymer is not recognised. */
export const OTHER_MATERIAL_BASE = 'other';

/** Family heading: "PA · нейлон", "PLA", "Другие материалы". */
export function materialBaseLabel(t: TFunction, base: string | null): string {
  if (base === null) return t('materialTypes.otherBase');
  const hint = t(`materialTypes.baseHint.${base}`, { defaultValue: '' });
  return hint ? `${base} · ${hint}` : base;
}

/** Groups with the caller's extra types merged in; unknown extras go to the "other" group. */
export function mergeMaterialTypes(groups: MaterialTypeGroup[], extra: string[]): MaterialTypeGroup[] {
  const known = new Set(groups.flatMap((group) => group.types.map((type) => type.toLowerCase())));
  const missing = extra.filter((type) => type && !known.has(type.toLowerCase()));
  if (missing.length === 0) return groups;
  const other = groups.find((group) => group.base === null);
  const rest = groups.filter((group) => group.base !== null);
  return [
    ...rest,
    {
      base: null,
      types: [...(other?.types ?? []), ...missing],
      filament_count: other?.filament_count ?? 0,
    },
  ];
}

/** Typing a family ("pa", "nylon") lists the whole family; otherwise matching types only. */
export function filterMaterialTypeGroups(
  groups: MaterialTypeGroup[],
  query: string,
  label: (base: string | null) => string,
): MaterialTypeGroup[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return groups;
  if (groups.some((group) => group.types.some((type) => type.toLowerCase() === needle))) {
    return groups;
  }
  return groups
    .map((group) =>
      label(group.base).toLowerCase().includes(needle)
        ? group
        : { ...group, types: group.types.filter((type) => type.toLowerCase().includes(needle)) },
    )
    .filter((group) => group.types.length > 0);
}

/** The family to show next to a manufacturer's type that does not name it ("Nylon" → "PA"). */
export function unnamedMaterialFamily(materialType: string, base: string | null | undefined): string | null {
  if (!base) return null;
  const compact = materialType.toUpperCase().replace(/[^A-Z0-9]/g, '');
  return compact.startsWith(base.replace(/[^A-Z0-9]/g, '')) ? null : base;
}
