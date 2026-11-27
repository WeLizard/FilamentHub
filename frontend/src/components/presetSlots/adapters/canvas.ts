import type { FeedTopologyChoice } from './types';
import type { Printer } from '../../../types/api';

// CANVAS is the multi-colour unit that SDCP printers and Elegoo's MQTT API
// report alike: four slots per unit, up to four units, and a spool holder
// (index 255) when no unit is attached. The plugin numbers a slot unit*4+place.
const CANVAS_SLOTS = 4;
const MAX_CANVAS_SLOTS = 16;
const SPOOL_HOLDER = 255;

export const CANVAS_TOPOLOGIES: FeedTopologyChoice[] = [
  { id: 'canvas', labelKey: 'printerSetup.feed.canvas', kind: 'mmu',
    count: { labelKey: 'printerSetup.feed.canvasSlots', initial: CANVAS_SLOTS, max: MAX_CANVAS_SLOTS },
    slots: (count) => Array.from({ length: count }, (_, provider_index) => ({ provider_index, kind: 'slot' })) },
  { id: 'single', labelKey: 'printerSetup.feed.canvasSingle', kind: 'direct_feed',
    slots: () => [{ provider_index: SPOOL_HOLDER, kind: 'external' }] },
];

/**
 * Which Elegoo Centauri a catalogue model is, read the way OrcaSlicer tells
 * them apart: a name ending in "2" is a Centauri Carbon 2. Anything else is
 * not a Centauri and gets null.
 */
export function centauriGeneration(model: Printer): 1 | 2 | null {
  if (!/^elegoo$/i.test(model.manufacturer?.trim() ?? '')) return null;
  const names = [model.model, model.name].map((value) => value?.trim() ?? '');
  if (!names.some((value) => /centauri/i.test(value))) return null;
  return names.some((value) => /centauri.*\b2$/i.test(value)) ? 2 : 1;
}
