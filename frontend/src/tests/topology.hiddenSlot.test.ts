import { describe, expect, it } from 'vitest';
import { setupTopologiesFor } from '../components/presetSlots/adapters';
import { topologyFromSystem, topologyPayload } from '../components/presetSlots/adapters/topology';
import type { MaterialSystem } from '../api/client';

const slot = (provider_index: number, kind: string, extra: object = {}) => ({
  id: provider_index + 1, provider_index, label: null, kind, active: true, assignment_revision: 0,
  assignment: null, legacy_projection: null, ...extra,
});

describe('topology of a system with a hidden external slot', () => {
  it('keeps a hidden slot out of the saved map even while it is displayed', () => {
    const choices = setupTopologiesFor('bambu', false);
    const system = { id: 1, name: 'AMS', kind: 'mmu', provider: 'bambu', active: true,
      slots: [slot(0, 'slot'), slot(1, 'slot'), slot(255, 'external', { user_visibility: 'hidden', displayed: true })],
    } as unknown as MaterialSystem;
    const selection = topologyFromSystem(choices, system);
    const payload = topologyPayload(choices, selection);
    expect(payload?.slots.map((item) => item.provider_index)).not.toContain(255);
  });
});
