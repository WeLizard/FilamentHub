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
  presetSlotsAPI: {
    assign: vi.fn(),
  },
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
        deviceId={1}
        deviceName="Device"
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
