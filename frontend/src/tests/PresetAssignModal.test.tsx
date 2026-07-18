import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const listMock = vi.fn();

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
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
    assignSlot: vi.fn(),
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
});
