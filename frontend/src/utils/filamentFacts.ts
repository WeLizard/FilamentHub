import { deriveVisualEffectsFromAdditives } from '../data/filamentFeatures';
import type { Filament, FilamentAdditive } from '../types/api';

export type FilamentCompositionFact =
  | {
      kind: 'additive';
      code: string;
      contentPercent: number | null;
      contentBasis: FilamentAdditive['content_basis'];
    }
  | {
      kind: 'effect';
      code: string;
    };

export const formatTemperatureRange = (
  minimum: number | null | undefined,
  maximum: number | null | undefined,
): string | null => {
  if (minimum == null && maximum == null) return null;
  if (minimum != null && maximum != null) {
    return minimum === maximum ? String(minimum) : `${minimum}\u2013${maximum}`;
  }
  return minimum != null ? `\u2265${minimum}` : `\u2264${maximum}`;
};

export const hasNonStandardDiameter = (diameter: number | null | undefined): boolean =>
  diameter != null && diameter !== 1.75;

export const getFilamentCompositionFacts = (
  filament: Pick<Filament, 'additives' | 'visual_settings'>,
): FilamentCompositionFact[] => {
  const additives = filament.additives ?? [];
  const derivedEffects = new Set(deriveVisualEffectsFromAdditives(additives));
  const storedEffects = filament.visual_settings?.effects?.length
    ? filament.visual_settings.effects
    : filament.visual_settings?.filler && filament.visual_settings.filler !== 'none'
      ? [filament.visual_settings.filler]
      : [];

  return [
    ...additives.map((additive) => ({
      kind: 'additive' as const,
      code: additive.code,
      contentPercent: additive.content_percent ?? null,
      contentBasis: additive.content_basis ?? null,
    })),
    ...[...new Set(storedEffects)]
      .filter((effect) => effect !== 'none' && !derivedEffects.has(effect))
      .map((effect) => ({ kind: 'effect' as const, code: effect })),
  ];
};
