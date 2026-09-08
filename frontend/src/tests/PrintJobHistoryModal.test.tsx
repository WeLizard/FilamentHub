import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const job = {
  id: 41,
  logical_id: 'job-41',
  physical_printer_id: 7,
  title: 'Two-colour part',
  status: 'completed',
  file_name: 'part.gcode',
  estimated_duration_s: null,
  actual_duration_s: 120,
  confirmed_consumption_g: 8.75,
  created_at: '2026-09-08T12:00:00Z',
  updated_at: '2026-09-08T12:02:00Z',
  materials: [],
  events: [],
  usage_segments: [
    {
      contract_version: 2,
      event_id: 'usage-1',
      segment_sequence: 1,
      event_type: 'checkpoint',
      reasons: ['tool_change'],
      observed_at: '2026-09-08T12:01:00Z',
      recorded_at: '2026-09-08T12:01:01Z',
      items: [
        {
          slot_index: 0,
          tool_index: 0,
          spool_id: 101,
          evidence: 'route_proof',
          confirmed_weight_g: 5.25,
        },
        {
          slot_index: 1,
          tool_index: 1,
          spool_id: 102,
          evidence: 'current_assignment',
          confirmed_weight_g: 3.5,
        },
      ],
    },
  ],
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values == null
        ? key
        : `${key}:${Object.entries(values)
            .filter(([name]) => name !== 'defaultValue')
            .map(([name, value]) => `${name}=${String(value)}`)
            .join(',')}`,
    i18n: { language: 'en' },
  }),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useQuery: ({ queryKey }: { queryKey: unknown[] }) =>
    queryKey[0] === 'print-jobs'
      ? { data: { items: [job], total: 1 }, isLoading: false, isError: false, isFetching: false }
      : { data: undefined, isLoading: false, isError: false, isFetching: false },
  useMutation: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('../api/client', () => ({
  calculatorAPI: { listHistory: vi.fn() },
  orcaSlicesAPI: { list: vi.fn() },
  printJobsAPI: { create: vi.fn(), list: vi.fn(), transition: vi.fn() },
  spoolsAPI: { list: vi.fn() },
}));

vi.mock('../components/Toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

describe('PrintJobHistoryModal usage segments', () => {
  it('keeps physical spools separate and states the evidence for each debit', async () => {
    const { PrintJobHistoryModal } = await import('../components/PrintJobHistoryModal');

    render(
      <PrintJobHistoryModal
        printer={{ id: 7, name: 'Workshop printer', material_systems: [] } as never}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'printJobs.expand' }));

    expect(screen.getByText('printJobs.usageSegments.sequence:count=1')).toBeInTheDocument();
    expect(screen.getByText('printJobs.usageSegments.spool:id=101')).toBeInTheDocument();
    expect(screen.getByText('printJobs.usageSegments.spool:id=102')).toBeInTheDocument();
    expect(screen.getByText('printJobs.usageSegments.evidence.route_proof')).toBeInTheDocument();
    expect(screen.getByText('printJobs.usageSegments.evidence.current_assignment')).toBeInTheDocument();
  });
});
