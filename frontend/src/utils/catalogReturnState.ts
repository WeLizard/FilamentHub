import type { FilamentColorGroup } from '../types/api';
import { FILAMENT_COLOR_GROUPS } from './filamentColorGroups';

export const CATALOG_FILTER_PARAMS = ['q', 'material', 'color', 'brand', 'printer', 'country'] as const;
export type CatalogFilterParam = typeof CATALOG_FILTER_PARAMS[number];

export interface CatalogUrlFilters {
  q: string;
  material: string | null;
  color: FilamentColorGroup | 'multicolor' | null;
  brand: number | null;
  printer: number | null;
  country: string | null;
}

export interface CatalogReturnMarker {
  version: 1;
  entryKey: string;
  catalogUrl: string;
  anchorId: string;
  scrollY: number;
  anchorOffset: number;
}

const RETURN_STATE_KEY = 'filamentHubCatalogReturn';
const COLOR_VALUES = new Set<string>([...FILAMENT_COLOR_GROUPS, 'multicolor']);

const boundedText = (value: string | null, maxLength: number): string | null => {
  if (value === null || value.length > maxLength || value.trim() === '') return null;
  return value;
};

const positiveInteger = (value: string | null): number | null => {
  if (value === null || !/^\d+$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
};

export function parseCatalogSearch(search: string): { filters: CatalogUrlFilters; canonicalSearch: string } {
  const params = new URLSearchParams(search);
  const q = boundedText(params.get('q'), 200) ?? '';
  const material = boundedText(params.get('material'), 128);
  const rawColor = params.get('color');
  const color = rawColor && COLOR_VALUES.has(rawColor)
    ? rawColor as FilamentColorGroup | 'multicolor'
    : null;
  const brand = positiveInteger(params.get('brand'));
  const printer = positiveInteger(params.get('printer'));
  const rawCountry = params.get('country');
  const country = rawCountry && /^[a-z]{2}$/i.test(rawCountry) ? rawCountry.toUpperCase() : null;
  const values: Record<CatalogFilterParam, string | null> = {
    q: q || null,
    material,
    color,
    brand: brand?.toString() ?? null,
    printer: printer?.toString() ?? null,
    country,
  };
  for (const name of CATALOG_FILTER_PARAMS) {
    const value = values[name];
    if (value === null) params.delete(name);
    else params.set(name, value);
  }
  return { filters: { q, material, color, brand, printer, country }, canonicalSearch: params.toString() };
}

export function updateCatalogSearch(search: string, name: CatalogFilterParam, value: string | number | null): string {
  const params = new URLSearchParams(search);
  if (value === null || value === '') params.delete(name);
  else params.set(name, String(value));
  return params.toString();
}

export const catalogItemAnchorId = (filamentId: number) => `catalog-filament-${filamentId}`;

export function recordCatalogReturn(marker: CatalogReturnMarker): void {
  if (typeof window === 'undefined') return;
  const currentState = window.history.state;
  const safeState = currentState && typeof currentState === 'object' ? currentState : {};
  window.history.replaceState({ ...safeState, [RETURN_STATE_KEY]: marker }, document.title);
}

export function readCatalogReturn(entryKey: string, catalogUrl: string): CatalogReturnMarker | null {
  if (typeof window === 'undefined') return null;
  const candidate = window.history.state?.[RETURN_STATE_KEY] as Partial<CatalogReturnMarker> | undefined;
  if (candidate?.version !== 1 || candidate.entryKey !== entryKey || candidate.catalogUrl !== catalogUrl
    || typeof candidate.anchorId !== 'string' || typeof candidate.scrollY !== 'number'
    || typeof candidate.anchorOffset !== 'number') return null;
  return candidate as CatalogReturnMarker;
}

export function isCatalogDetailOrigin(value: unknown): value is { from: 'catalog'; catalogEntryKey: string } {
  if (!value || typeof value !== 'object') return false;
  const state = value as Record<string, unknown>;
  return state.from === 'catalog' && typeof state.catalogEntryKey === 'string' && state.catalogEntryKey.length > 0;
}

export function navigateBackToCatalog(
  navigate: { (delta: number): void; (to: string): void },
  locationState: unknown,
): void {
  if (isCatalogDetailOrigin(locationState)) navigate(-1);
  else navigate('/');
}
