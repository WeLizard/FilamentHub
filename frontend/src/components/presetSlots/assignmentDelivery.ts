import {
  physicalPrintersAPI,
  type MaterialSlot,
  type MaterialSystem,
  type PhysicalPrinter,
  type SlotAssignPayload,
} from '../../api/client';
import { feedAdapterFor } from './adapters';
import type { MaterialDeliveryResult } from './adapters/types';

export const ASSIGNMENT_DELIVERY_FEEDBACK_KEY = 'preset-slot-assignment-delivery';

export interface AssignmentDeliveryOutcome {
  printer: PhysicalPrinter;
  system: MaterialSystem | null;
  slot: MaterialSlot | null;
  delivery: MaterialDeliveryResult | null;
}

export interface AssignmentDeliveryNotice {
  tone: 'success' | 'info' | 'error';
  key: string;
}

// These codes come from the provider adapters' immediate write paths. Keep the
// saved assignment explicit while telling the person why local delivery did
// not happen or could not be verified.
const SAVED_ONLY_REASON_KEYS: Record<string, string> = {
  host_unavailable: 'presetSlots.delivery.savedOnlyHostUnavailable',
  preset_not_loaded: 'presetSlots.delivery.savedOnlyPresetNotLoaded',
  printer_busy: 'presetSlots.delivery.savedOnlyPrinterBusy',
  rfid_managed: 'presetSlots.delivery.savedOnlyRfidManaged',
  pull_required: 'presetSlots.delivery.savedOnlyPullRequired',
  spool_ids_unavailable: 'presetSlots.delivery.savedOnlySpoolIdsUnavailable',
  slot_empty: 'presetSlots.delivery.savedOnlySlotEmpty',
  material_mismatch: 'presetSlots.delivery.savedOnlyMaterialMismatch',
  spool_facts_unavailable: 'presetSlots.delivery.savedOnlySpoolFactsUnavailable',
  snapshot_failed: 'presetSlots.delivery.savedOnlySnapshotFailed',
  unreachable: 'presetSlots.delivery.savedOnlyUnreachable',
  verification_failed: 'presetSlots.delivery.savedOnlyVerificationFailed',
  not_applied: 'presetSlots.delivery.savedOnlyNotApplied',
  command_failed: 'presetSlots.delivery.savedOnlyCommandFailed',
  connection_not_found: 'presetSlots.delivery.savedOnlyConnectionNotFound',
  stale_assignment: 'presetSlots.delivery.savedOnlyStaleAssignment',
  expired: 'presetSlots.delivery.savedOnlyExpired',
  assignment_incomplete: 'presetSlots.delivery.savedOnlyAssignmentIncomplete',
};

export function assignmentDeliveryNotice(
  outcome: AssignmentDeliveryOutcome,
): AssignmentDeliveryNotice | null {
  if (outcome.delivery?.physicallyApplied) {
    return { tone: 'error', key: 'presetSlots.delivery.observationUploadFailed' };
  }
  if (outcome.delivery?.status === 'delivered') {
    return { tone: 'success', key: 'presetSlots.delivery.delivered' };
  }
  if (outcome.delivery?.status === 'unsupported') {
    return { tone: 'info', key: 'presetSlots.delivery.clearUnsupported' };
  }
  if (outcome.delivery?.status === 'saved_only') {
    const reason = outcome.delivery.code
      ? SAVED_ONLY_REASON_KEYS[outcome.delivery.code]
      : undefined;
    return { tone: 'info', key: reason ?? 'presetSlots.delivery.savedOnly' };
  }
  return null;
}

/**
 * Commit desired state first, then ask its provider adapter to accelerate that
 * exact committed slot. A local delivery failure never rolls back the saved
 * server assignment.
 */
export async function assignMaterialSlot(
  physicalPrinterId: number,
  materialSystemId: number,
  materialSlotId: number,
  payload: SlotAssignPayload,
): Promise<AssignmentDeliveryOutcome> {
  const printer = await physicalPrintersAPI.assignSlot(
    physicalPrinterId,
    materialSlotId,
    payload,
  );
  const system = (printer.material_systems ?? []).find(
    (item) => item.id === materialSystemId,
  ) ?? null;
  const slot = system?.slots.find((item) => item.id === materialSlotId) ?? null;
  if (!system || !slot) {
    return { printer, system, slot, delivery: { status: 'saved_only', code: 'commit_missing' } };
  }

  const deliver = feedAdapterFor(system.provider).deliverAssignment;
  if (!deliver) return { printer, system, slot, delivery: null };

  try {
    const delivery = await deliver({ printer, system, slot });
    return { printer, system, slot, delivery };
  } catch {
    return {
      printer,
      system,
      slot,
      delivery: { status: 'saved_only', code: 'host_unavailable' },
    };
  }
}
