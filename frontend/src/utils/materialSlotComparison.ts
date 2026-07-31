import type { GateState, MaterialSlot, UserSpool } from '../api/client';

export type MaterialSlotConflict =
  | 'assigned_but_observed_empty'
  | 'observed_loaded_without_spool'
  | 'observed_details_differ'
  | null;

export type MaterialSlotObservationState = 'none' | 'unknown' | 'empty' | 'loaded' | 'buffer';

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

function observationState(slot: MaterialSlot): MaterialSlotObservationState {
  const observation = slot.legacy_projection;
  if (
    observation?.hh_status == null
    && observation?.hh_material == null
    && observation?.hh_color_hex == null
  ) {
    // Happy Hare's Spoolman-compatible path can confirm a gate assignment
    // without sending the richer legacy material/color/status snapshot. The
    // source still proves that this state came from the provider rather than
    // from a click in FilamentHub.
    if (observation?.source === 'hh_snapshot') {
      return observation.spool_id != null ? 'loaded' : 'empty';
    }
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
): MaterialSlotComparison {
  const desiredPresetId = slot.assignment?.preset_id ?? gate?.preset_id ?? null;
  const desiredSpoolId = slot.assignment?.spool_id ?? gate?.spool_id ?? null;
  const observation = slot.legacy_projection;
  const state = observationState(slot);

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
