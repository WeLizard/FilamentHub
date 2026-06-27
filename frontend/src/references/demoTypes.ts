/**
 * Reference / scaffold types kept out of the main API types.
 *
 * Not used by any component right now. Preserved as a draft for a future
 * "filament with computed brand/rating" shape; move back into types/api.ts
 * and wire up when the feature it was sketched for is implemented.
 */
import type { Brand, Filament, Preset } from '../types/api';

/** Filament enriched with computed fields (brand, ratings, preset rollups). */
export interface FilamentWithBrand extends Filament {
  brand?: Brand;
  rating?: number; // Вычисляется из пресетов
  successRate?: number; // Вычисляется из пресетов
  officialPreset?: Preset;
  communityPresets?: Preset[];
}
