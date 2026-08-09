import type { Brand, Filament } from '../types/api';

export function brandPublicPath(brand: Pick<Brand, 'slug'>): string {
  return `/brands/${brand.slug}`;
}

export function filamentPublicPath(
  filament: Pick<Filament, 'id' | 'slug' | 'brand_slug'>,
): string {
  if (filament.brand_slug && filament.slug) {
    return `/brands/${filament.brand_slug}/filaments/${filament.slug}`;
  }
  // Compatibility for responses from an older backend during a rolling deploy.
  return `/filaments/${filament.id}`;
}

export function filamentVariantLabel(
  filament: Pick<Filament, 'name' | 'color_name'>,
): string {
  const name = filament.name.trim();
  const colorName = filament.color_name?.trim();
  if (!colorName) {
    return name;
  }

  const normalizeWords = (value: string) => value
    .toLocaleLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim();
  const normalizedName = ` ${normalizeWords(name)} `;
  const normalizedColor = normalizeWords(colorName);
  if (normalizedColor && normalizedName.includes(` ${normalizedColor} `)) {
    return name;
  }
  return `${name} — ${colorName}`;
}
