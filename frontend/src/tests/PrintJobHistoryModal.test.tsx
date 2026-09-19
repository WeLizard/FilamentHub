import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  listCalculations: vi.fn(),
  getCalculation: vi.fn(),
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
  estimated_consumption_g: 10.5,
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
          estimated_weight_g: 6,
        },
        {
          slot_index: 1,
          tool_index: 1,
          spool_id: 102,
          evidence: 'current_assignment',
          confirmed_weight_g: 3.5,
          estimated_weight_g: 4.5,
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
  calculatorAPI: {
    listHistoryFeed: apiMocks.listCalculations,
    getHistory: apiMocks.getCalculation,
  },
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
  apiMocks.getCalculation.mockResolvedValue({ parsed_jobs: [] });
});

describe('PrintJobHistoryModal usage segments', () => {
  it('shows unresolved reports separately from confirmed consumption', async () => {
    apiMocks.listJobs.mockResolvedValue({
      items: [{ ...job, confirmed_consumption_g: 0, unreconciled_consumption_g: 5,
        usage_segments: [{ ...job.usage_segments[0], items: [{
          ...job.usage_segments[0].items[0], confirmed_weight_g: 0, unreconciled_weight_g: 5,
        }] }],
      }], total: 1,
    });
    await renderModal();
    fireEvent.click(await screen.findByRole('button', { name: 'printJobs.expand' }));
    expect(screen.getAllByText('printJobs.needsReconciliation:value=5')).toHaveLength(2);
    expect(screen.queryByText('printJobs.confirmedConsumption:value=5')).not.toBeInTheDocument();
  });
  it('keeps physical spools separate and states the evidence for each debit', async () => {
    await renderModal();

    fireEvent.click(await screen.findByRole('button', { name: 'printJobs.expand' }));

    expect(screen.getByText('printJobs.usageSegments.sequence:count=1')).toBeInTheDocument();
    expect(screen.getByText('printJobs.usageSegments.spool:id=101')).toBeInTheDocument();
    expect(screen.getByText('printJobs.usageSegments.spool:id=102')).toBeInTheDocument();
    expect(screen.getByText('printJobs.usageSegments.evidence.route_proof')).toBeInTheDocument();
    expect(screen.getByText('printJobs.usageSegments.evidence.current_assignment')).toBeInTheDocument();
    expect(screen.getByText('printJobs.estimatedConsumption:value=11')).toBeInTheDocument();
    expect(screen.getByText('printJobs.usageSegments.estimatedWeight:value=6')).toBeInTheDocument();
  });

  it('retains three query pages, reaches the terminal cursor, and hydrates a page-three item', async () => {
    apiMocks.listCalculations.mockImplementation(async ({ cursor }: { cursor?: string | null }) => (
      cursor === 'page-3'
        ? {
            items: [{ id: 52, title: 'Estimate on third page' }],
            total: 52,
            next_cursor: null,
          }
        : cursor === 'page-2'
          ? {
              items: [{ id: 51, title: 'Estimate on second page' }],
              total: 52,
              next_cursor: 'page-3',
            }
        : {
            items: [{ id: 50, title: 'Estimate on first page' }],
            total: 52,
            next_cursor: 'page-2',
          }
    ));
    apiMocks.getCalculation.mockResolvedValue({
      id: 52,
      title: 'Estimate on third page',
      parsed_jobs: [{ job_key: 'plate-3', parsed_gcode: { file_name: 'plate-3.gcode' } }],
    });
    await renderModal();

    fireEvent.click(screen.getByRole('button', { name: 'printJobs.new' }));
    expect(await screen.findByRole('option', { name: 'Estimate on first page' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Estimate on third page' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'profilePage.calculator.historyLoadMore' }));
    expect(await screen.findByRole('option', { name: 'Estimate on second page' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'profilePage.calculator.historyLoadMore' }));
    const thirdPageOption = await screen.findByRole('option', { name: 'Estimate on third page' });
    expect(screen.queryByRole('button', { name: 'profilePage.calculator.historyLoadMore' })).not.toBeInTheDocument();

    const calculationSelect = screen.getByRole('combobox', { name: 'printJobs.fields.calculation' });
    fireEvent.change(calculationSelect, { target: { value: '52' } });
    expect(calculationSelect).toHaveValue('52');
    expect(screen.getByRole('textbox', { name: 'printJobs.fields.name' })).toHaveValue('Estimate on third page');
    expect(thirdPageOption).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.getCalculation).toHaveBeenCalledWith(52, expect.any(AbortSignal)));
    expect(apiMocks.listCalculations).toHaveBeenNthCalledWith(
      3,
      { limit: 50, cursor: 'page-3' },
      expect.any(AbortSignal),
    );
  });

  it('shows a retryable detail error before allowing a selected calculation', async () => {
    apiMocks.listCalculations.mockResolvedValue({
      items: [{ id: 60, title: 'Needs hydration' }],
      total: 1,
      next_cursor: null,
    });
    apiMocks.getCalculation
      .mockRejectedValueOnce(new Error('detail unavailable'))
      .mockResolvedValueOnce({ id: 60, title: 'Needs hydration', parsed_jobs: [] });
    await renderModal();
    fireEvent.click(screen.getByRole('button', { name: 'printJobs.new' }));
    const calculationSelect = await screen.findByRole('combobox', { name: 'printJobs.fields.calculation' });
    fireEvent.change(calculationSelect, { target: { value: '60' } });

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('profilePage.calculator.historyLoadError');
    fireEvent.click(screen.getByRole('button', { name: /common\.retry/ }));
    await waitFor(() => expect(apiMocks.getCalculation).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText('profilePage.calculator.historyLoadError')).not.toBeInTheDocument());
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
