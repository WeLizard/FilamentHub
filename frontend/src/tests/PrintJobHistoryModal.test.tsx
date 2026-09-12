import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  listCalculations: vi.fn(),
  listJobs: vi.fn(),
  listSlices: vi.fn(),
  listSpools: vi.fn(),
}));

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

vi.mock('../api/client', () => ({
  calculatorAPI: { listHistory: apiMocks.listCalculations },
  orcaSlicesAPI: { list: apiMocks.listSlices },
  printJobsAPI: {
    create: vi.fn(),
    list: apiMocks.listJobs,
    transition: vi.fn(),
  },
  spoolsAPI: { list: apiMocks.listSpools },
}));

vi.mock('../components/Toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const printer = { id: 7, name: 'Workshop printer', material_systems: [] } as never;

async function renderModal() {
  const { PrintJobHistoryModal } = await import('../components/PrintJobHistoryModal');
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <PrintJobHistoryModal printer={printer} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.listJobs.mockResolvedValue({ items: [job], total: 1 });
  apiMocks.listSlices.mockResolvedValue([]);
  apiMocks.listSpools.mockResolvedValue([]);
  apiMocks.listCalculations.mockResolvedValue({ items: [], total: 0, next_cursor: null });
});

describe('PrintJobHistoryModal usage segments', () => {
  it('keeps physical spools separate and states the evidence for each debit', async () => {
    await renderModal();

    fireEvent.click(await screen.findByRole('button', { name: 'printJobs.expand' }));

    expect(screen.getByText('printJobs.usageSegments.sequence:count=1')).toBeInTheDocument();
    expect(screen.getByText('printJobs.usageSegments.spool:id=101')).toBeInTheDocument();
    expect(screen.getByText('printJobs.usageSegments.spool:id=102')).toBeInTheDocument();
    expect(screen.getByText('printJobs.usageSegments.evidence.route_proof')).toBeInTheDocument();
    expect(screen.getByText('printJobs.usageSegments.evidence.current_assignment')).toBeInTheDocument();
  });

  it('appends a real second query page, reaches the terminal cursor, and selects its item', async () => {
    apiMocks.listCalculations.mockImplementation(async ({ cursor }: { cursor?: string | null }) => (
      cursor === 'next-page'
        ? {
            items: [{ id: 51, title: 'Estimate beyond first page', parsed_jobs: [] }],
            total: 51,
            next_cursor: null,
          }
        : {
            items: [{ id: 50, title: 'Estimate on first page', parsed_jobs: [] }],
            total: 51,
            next_cursor: 'next-page',
          }
    ));
    await renderModal();

    fireEvent.click(screen.getByRole('button', { name: 'printJobs.new' }));
    expect(await screen.findByRole('option', { name: 'Estimate on first page' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Estimate beyond first page' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'profilePage.calculator.historyLoadMore' }));
    const secondPageOption = await screen.findByRole('option', { name: 'Estimate beyond first page' });
    expect(screen.queryByRole('button', { name: 'profilePage.calculator.historyLoadMore' })).not.toBeInTheDocument();

    const calculationSelect = screen.getByRole('combobox', { name: 'printJobs.fields.calculation' });
    fireEvent.change(calculationSelect, { target: { value: '51' } });
    expect(calculationSelect).toHaveValue('51');
    expect(screen.getByRole('textbox', { name: 'printJobs.fields.name' })).toHaveValue('Estimate beyond first page');
    expect(secondPageOption).toBeInTheDocument();
    expect(apiMocks.listCalculations).toHaveBeenNthCalledWith(
      2,
      { size: 50, cursor: 'next-page' },
      expect.any(AbortSignal),
    );
  });

  it('shows initial loading and a retryable error instead of an empty selector', async () => {
    let rejectInitial!: (reason: Error) => void;
    const initialRequest = new Promise((_resolve, reject) => {
      rejectInitial = reject;
    });
    apiMocks.listCalculations
      .mockReturnValueOnce(initialRequest)
      .mockResolvedValueOnce({
        items: [{ id: 1, title: 'Recovered estimate', parsed_jobs: [] }],
        total: 1,
        next_cursor: null,
      });
    await renderModal();

    fireEvent.click(screen.getByRole('button', { name: 'printJobs.new' }));
    expect(screen.getByRole('status')).toHaveTextContent('profilePage.calculator.historyLoading');
    expect(screen.queryByRole('combobox', { name: 'printJobs.fields.calculation' })).not.toBeInTheDocument();

    await act(async () => rejectInitial(new Error('history unavailable')));
    expect(await screen.findByRole('alert')).toHaveTextContent('profilePage.calculator.historyLoadError');
    expect(screen.queryByRole('combobox', { name: 'printJobs.fields.calculation' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /common\.retry/ }));
    await waitFor(() => expect(apiMocks.listCalculations).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole('option', { name: 'Recovered estimate' })).toBeInTheDocument();
  });
});
