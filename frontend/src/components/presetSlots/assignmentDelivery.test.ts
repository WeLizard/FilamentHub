import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  assignSlot: vi.fn(),
  deliverAssignment: vi.fn(),
  feedAdapterFor: vi.fn(),
}));

vi.mock('../../api/client', () => ({
  physicalPrintersAPI: { assignSlot: mocks.assignSlot },
}));

vi.mock('./adapters', () => ({
  feedAdapterFor: mocks.feedAdapterFor,
}));

import {
  assignmentDeliveryNotice,
  assignMaterialSlot,
} from './assignmentDelivery';

const committedPrinter = {
  id: 7,
  material_systems: [{
    id: 8,
    provider: 'bambu',
    slots: [{
      id: 9,
      provider_index: 5,
      assignment_revision: 12,
      assignment: {
        preset_id: 41,
        spool_id: 301,
        source_ts: '2026-09-05T12:00:00Z',
      },
    }],
  }],
} as any;

describe('assignment delivery coordinator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.assignSlot.mockResolvedValue(committedPrinter);
    mocks.feedAdapterFor.mockReturnValue({ deliverAssignment: mocks.deliverAssignment });
  });

  it('delivers the exact slot returned by the successful server commit', async () => {
    mocks.deliverAssignment.mockResolvedValue({ status: 'delivered' });

    const outcome = await assignMaterialSlot(7, 8, 9, {
      expected_revision: 11,
      expected_spool_id: null,
      preset_id: 41,
      spool_id: 301,
    });

    expect(mocks.assignSlot).toHaveBeenCalledWith(7, 9, {
      expected_revision: 11,
      expected_spool_id: null,
      preset_id: 41,
      spool_id: 301,
    });
    expect(mocks.feedAdapterFor).toHaveBeenCalledWith('bambu');
    expect(mocks.deliverAssignment).toHaveBeenCalledWith({
      printer: committedPrinter,
      system: committedPrinter.material_systems[0],
      slot: committedPrinter.material_systems[0].slots[0],
    });
    expect(outcome.delivery).toEqual({ status: 'delivered' });
  });

  it('keeps the saved assignment when local delivery is unavailable', async () => {
    mocks.deliverAssignment.mockRejectedValue(new Error('host offline'));

    const outcome = await assignMaterialSlot(7, 8, 9, {
      expected_revision: 11,
      expected_spool_id: null,
      preset_id: 41,
      spool_id: 301,
    });

    expect(mocks.assignSlot).toHaveBeenCalledTimes(1);
    expect(outcome.printer).toBe(committedPrinter);
    expect(outcome.delivery).toEqual({
      status: 'saved_only',
      code: 'host_unavailable',
    });
    expect(assignmentDeliveryNotice(outcome)).toEqual({
      tone: 'info',
      key: 'presetSlots.delivery.savedOnly',
    });
  });

  it('reports an unconfirmed observation upload after a proven physical write', () => {
    expect(assignmentDeliveryNotice({
      printer: committedPrinter,
      system: committedPrinter.material_systems[0],
      slot: committedPrinter.material_systems[0].slots[0],
      delivery: {
        status: 'saved_only',
        code: 'snapshot_failed',
        physicallyApplied: true,
      },
    })).toEqual({
      tone: 'error',
      key: 'presetSlots.delivery.observationUploadFailed',
    });
  });
});
