import type { GateState, MaterialSlot, UserSpool } from '../api/client';

export type MaterialSlotConflict =
  | 'assigned_but_observed_empty'
  | 'observed_loaded_without_spool'
  | 'observed_details_differ'
  | null;

export type MaterialSlotObservationState = 'none' | 'unknown' | 'empty' | 'loaded' | 'buffer';

export const MATERIAL_SLOT_OBSERVATION_FRESH_MS = 5 * 60_000;

export interface MaterialSlotComparison {
  desiredPresetId: number | null;
  desiredSpoolId: number | null;
  observationState: MaterialSlotObservationState;
  observedMaterial: string | null;
  observedColorHex: string | null;
  conflict: MaterialSlotConflict;
}

function normalizeMaterial(value: string | null | undefined): string | null {
  const normalized = value?.trim().replace(/\s+/g, ' ').toLocaleUpperCase();
  return normalized || null;
}

function normalizeHex(value: string | null | undefined): string | null {
  const normalized = value?.trim().replace(/^#/, '').toLocaleUpperCase();
  return normalized && /^[0-9A-F]{6}$/.test(normalized) ? normalized : null;
}

function observationState(
  slot: MaterialSlot,
  now: number,
): MaterialSlotObservationState {
  const observation = slot.legacy_projection;
  if (observation?.source !== 'hh_snapshot') return 'none';

  const observedAt = new Date(observation.source_ts).getTime();
  const age = now - observedAt;
  if (
    !Number.isFinite(observedAt)
    || age > MATERIAL_SLOT_OBSERVATION_FRESH_MS
    || age < -60_000
  ) {
    return 'none';
  }

  if (
    observation?.hh_status == null
    && observation?.hh_material == null
    && observation?.hh_color_hex == null
  ) {
    // A provider-side spool association is evidence about an assignment, not
    // proof that hardware currently has filament loaded or that a gate is empty.
    return 'none';
  }
  if (observation.hh_status === 0) return 'empty';
  if (observation.hh_status === 2) return 'buffer';
  if (
    observation.hh_status === 1
    || observation.hh_material != null
    || observation.hh_color_hex != null
  ) {
    return 'loaded';
  }
  return 'unknown';
}

/**
 * Compares the user's desired assignment with adapter telemetry.
 *
 * Material and color are only supporting evidence. They may flag a review,
 * but they never identify or assign a physical spool automatically.
 */
export function compareMaterialSlot(
  slot: MaterialSlot,
  gate: GateState | null,
  desiredSpool: UserSpool | null,
  now: number = Date.now(),
): MaterialSlotComparison {
  const desiredPresetId = slot.assignment?.preset_id ?? gate?.preset_id ?? null;
  const desiredSpoolId = slot.assignment?.spool_id ?? gate?.spool_id ?? null;
  const observation = slot.legacy_projection;
  const state = observationState(slot, now);

  let conflict: MaterialSlotConflict = null;
  if (state === 'empty' && (desiredPresetId != null || desiredSpoolId != null)) {
    conflict = 'assigned_but_observed_empty';
  } else if ((state === 'loaded' || state === 'buffer') && desiredSpoolId == null) {
    conflict = 'observed_loaded_without_spool';
  } else if ((state === 'loaded' || state === 'buffer') && desiredSpool?.filament) {
    const desiredMaterial = normalizeMaterial(desiredSpool.filament.material_type);
    const observedMaterial = normalizeMaterial(observation?.hh_material);
    const desiredColor = normalizeHex(desiredSpool.filament.color_hex);
    const observedColor = normalizeHex(observation?.hh_color_hex);
    if (
      (desiredMaterial != null && observedMaterial != null && desiredMaterial !== observedMaterial)
      || (desiredColor != null && observedColor != null && desiredColor !== observedColor)
    ) {
      conflict = 'observed_details_differ';
    }
  }

  return {
    desiredPresetId,
    desiredSpoolId,
    observationState: state,
    observedMaterial: observation?.hh_material ?? null,
    observedColorHex: normalizeHex(observation?.hh_color_hex),
    conflict,
  };
}
