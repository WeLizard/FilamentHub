import type { FeedTopologyChoice } from './types';
import type { MaterialSystem } from '../../../api/client';

export const ordinaryTopologies: FeedTopologyChoice[] = [
  { id: 'direct', labelKey: 'printerSetup.feed.single', kind: 'direct_feed',
    slots: () => [{ provider_index: 0, kind: 'external' }] },
  { id: 'tools', labelKey: 'printerSetup.feed.tools', kind: 'multi_tool',
    count: { labelKey: 'printerSetup.feed.toolCount', initial: 2, max: 256 },
    slots: (count) => Array.from({ length: count }, (_, provider_index) => ({ provider_index, kind: 'tool' })) },
  { id: 'changer', labelKey: 'printerSetup.feed.changer', kind: 'mmu',
    count: { labelKey: 'printerSetup.feed.slotCount', initial: 4, max: 256 },
    slots: (count) => Array.from({ length: count }, (_, provider_index) => ({ provider_index, kind: 'slot' })) },
];

export interface TopologySelection {
  choice: string;
  count: string;
  extras: number[];
  routes?: Array<{ provider_index: number; kind: string; label?: string | null }>;
}

export function initialTopology(choice: FeedTopologyChoice): TopologySelection {
  return { choice: choice.id, count: String(choice.count?.initial ?? 1),
    extras: (choice.extras ?? []).filter((extra) => extra.checked).map((extra) => extra.index) };
}

export function topologyFromSystem(choices: FeedTopologyChoice[], system?: MaterialSystem): TopologySelection {
  const provider = system?.provider === 'legacy' ? 'manual' : system?.provider;
  const choice = choices.find((item) => item.kind === system?.kind && item.provider === provider)
    ?? choices.find((item) => item.kind === system?.kind) ?? choices[0];
  if (!system) return initialTopology(choice);
  const extraIndices = new Set(choice.extras?.map((item) => item.index));
  const slots = system.slots.filter((slot) => slot.active);
  if (slots.length === 0) return initialTopology(choice);
  return { choice: choice.id,
    count: String(slots.filter((slot) => !extraIndices.has(slot.provider_index)).length || choice.count?.initial || 1),
    extras: slots.filter((slot) => extraIndices.has(slot.provider_index)).map((slot) => slot.provider_index),
    ...(choice.kind === system.kind ? { routes: slots.map(({ provider_index, kind, label }) => ({ provider_index, kind, label })) } : {}) };
}

export function topologyPayload(choices: FeedTopologyChoice[], selection: TopologySelection) {
  const choice = choices.find((item) => item.id === selection.choice) ?? choices[0];
  const count = choice.count ? Number(selection.count) : 1;
  if (!Number.isInteger(count) || count < 1 || count > (choice.count?.max ?? 1)) return null;
  const extras = new Set(choice.extras?.map((item) => item.index));
  const slots = [...(selection.routes?.filter((route) => !extras.has(route.provider_index)) ?? choice.slots(count)), ...(choice.extras ?? [])
    .filter((extra) => selection.extras.includes(extra.index))
    .map((extra) => selection.routes?.find((route) => route.provider_index === extra.index)
      ?? { provider_index: extra.index, kind: extra.kind })];
  if (slots.length > 257 || new Set(slots.map((slot) => slot.provider_index)).size !== slots.length) return null;
  return { kind: choice.kind, slots };
}
