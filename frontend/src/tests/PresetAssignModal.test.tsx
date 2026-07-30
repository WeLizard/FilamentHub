import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const listMock = vi.fn();
const assignSlotMock = vi.fn();
const invalidateQueriesMock = vi.fn();

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({
    invalidateQueries: invalidateQueriesMock,
  }),
  useQuery: ({ queryFn }: { queryFn: () => Promise<unknown> }) => {
    void queryFn();
    return { data: { items: [] }, isLoading: false };
  },
}));

vi.mock('../api/client', () => ({
  presetsAPI: {
    list: listMock,
  },
  physicalPrintersAPI: {
    assignSlot: assignSlotMock,
  },
  savedPresetsAPI: {
    list: vi.fn().mockResolvedValue({ items: [] }),
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1 } }),
}));

vi.mock('../components/Toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('PresetAssignModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listMock.mockResolvedValue({ items: [] });
    assignSlotMock.mockResolvedValue({});
    invalidateQueriesMock.mockResolvedValue(undefined);
  });

  it('should_request_presets_without_user_id_filter', async () => {
    const { PresetAssignModal } = await import('../components/presetSlots/PresetAssignModal');

    render(
      <PresetAssignModal
        isOpen
        gateIndex={0}
        gate={null}
        physicalPrinterId={1}
        materialSlotId={10}
        deviceName="Device"
        systemName="MMU"
        provider="manual"
        spools={[]}
        onClose={vi.fn()}
        onAssigned={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(listMock).toHaveBeenCalled();
    });

    const firstCall = listMock.mock.calls[0][0] as Record<string, unknown>;
    expect(firstCall).not.toHaveProperty('user_id');
    expect(firstCall).toMatchObject({
      page: 1,
      size: 50,
      active_only: true,
    });
  });

  it('refreshes both standalone and profile spool caches after assignment', async () => {
    const { PresetAssignModal } = await import('../components/presetSlots/PresetAssignModal');

    render(
      <PresetAssignModal
        isOpen
        gateIndex={0}
        gate={null}
        physicalPrinterId={1}
        materialSlotId={10}
        deviceName="Device"
        systemName="MMU"
        provider="happy_hare"
        spools={[
          {
            id: 23,
            user_id: 1,
            filament_id: null,
            initial_weight_g: 1000,
            used_weight_g: 123,
            remaining_weight_g: 877,
            remaining_pct: 87.7,
            state: 'shelf',
            source: 'manual',
            price: null,
            lot_nr: null,
            comment: null,
            extra: null,
            filament: null,
            created_at: '2026-07-30T00:00:00Z',
            updated_at: '2026-07-30T00:00:00Z',
            last_used_at: null,
          },
        ]}
        onClose={vi.fn()}
        onAssigned={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText('profilePage.spoolNoFilament'));
    fireEvent.click(screen.getByText('presetSlots.modal.assign'));

    await waitFor(() => {
      expect(assignSlotMock).toHaveBeenCalledWith(1, 10, {
        preset_id: null,
        spool_id: 23,
      });
    });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: ['physical-printers'],
    });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ['spools'] });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: ['user-spools'],
    });
  });
});
