import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import type { OrcaSliceReport } from '../../types/api';
import { SlicedJobsPanel } from './SlicedJobsPanel';

const slice = (id: number, name: string): OrcaSliceReport => ({
  id,
  file_name: name,
  source_key: `key-${id}`,
  printer_model: 'Voron 2.4',
  physical_printer_name: null,
  received_at: '2026-09-30T10:00:00Z',
  sliced_at: '2026-09-30T10:00:00Z',
} as OrcaSliceReport);

const slicesApi = vi.hoisted(() => ({ list: vi.fn(), remove: vi.fn() }));
vi.mock('../../api/client', () => ({ orcaSlicesAPI: slicesApi }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

const renderPanel = (props: Partial<React.ComponentProps<typeof SlicedJobsPanel>>) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SlicedJobsPanel onPick={vi.fn()} {...props} />
    </QueryClientProvider>,
  );

describe('SlicedJobsPanel while a slice is being read', () => {
  it('shows how far the read has got and holds the other slices back', async () => {
    slicesApi.list.mockResolvedValue([slice(1, 'long.gcode'), slice(2, 'other.gcode')]);

    renderPanel({ pickingId: 1, pickingProgress: 0.426 });

    await waitFor(() => expect(screen.getByText('43%')).toBeTruthy());
    const buttons = screen.getAllByRole('button').filter((button) => button.className.includes('bg-cyan-500/15'));
    expect(buttons).toHaveLength(2);
    expect(buttons.every((button) => (button as HTMLButtonElement).disabled)).toBe(true);
    expect(screen.getByText('slicedJobs.use')).toBeTruthy();
  });

  it('offers every slice again once nothing is being read', async () => {
    slicesApi.list.mockResolvedValue([slice(1, 'long.gcode')]);

    renderPanel({ pickingId: null, pickingProgress: null });

    const button = await screen.findByText('slicedJobs.use');
    expect((button as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText(/%$/)).toBeNull();
  });
});
