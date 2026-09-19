import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { UserSpool } from '../api/client';
import { SpoolUsageModal } from './SpoolUsageModal';

const api = vi.hoisted(() => ({
  usage: vi.fn(),
  revertUsage: vi.fn(),
}));

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  spoolsAPI: {
    usage: api.usage,
    revertUsage: api.revertUsage,
  },
}));
vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));
vi.mock('./ModalOverlay', () => ({
  ModalOverlay: ({ children }: { children: ReactNode }) => <div role="dialog">{children}</div>,
}));
vi.mock('./Toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const spool = {
  id: 41,
  initial_weight_g: 1000,
  used_weight_g: 20,
  filament: { name: 'PLA' },
} as UserSpool;

function renderModal(event: Record<string, unknown>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SpoolUsageModal spool={spool} isOpen onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe('SpoolUsageModal warnings', () => {
  it('does not offer to return grams from an unapplied estimate', async () => {
    api.usage.mockResolvedValue([{
      id: 5, event_type: 'print_estimate', delta_weight_g: 30,
      remaining_weight_g: null, device_name: 'Printer', job_ref: null,
      created_at: '2026-09-19T10:00:00Z', meta: null,
    }]);
    renderModal({});
    await screen.findByText('spoolUsage.source.print_estimate');
    expect(screen.queryByTitle('spoolUsage.revert')).not.toBeInTheDocument();
    expect(screen.getByText('≈30 spoolUsage.grams')).toBeInTheDocument();
  });
  beforeEach(() => {
    api.usage.mockReset();
    api.revertUsage.mockReset();
  });

  it('does not warn when the reported amount equals the applied amount', async () => {
    api.usage.mockResolvedValue([{
      id: 1, event_type: 'printer_report', delta_weight_g: 20,
      remaining_weight_g: 980, device_name: 'Printer', job_ref: null,
      created_at: '2026-09-19T10:00:00Z',
      meta: { reported_weight_g: 20 },
    }]);
    renderModal({});

    await screen.findByText('Printer');
    expect(screen.queryByText('spoolUsage.warnReported')).not.toBeInTheDocument();
  });

  it.each([
    ['already_in_balance', 'spoolUsage.alreadyInBalance'],
    ['needs_reconciliation', 'spoolUsage.needsReconciliation'],
  ])('shows the precise %s accounting warning', async (balanceAccounting, key) => {
    api.usage.mockResolvedValue([{
      id: 2, event_type: 'printer_report', delta_weight_g: 20,
      remaining_weight_g: 980, device_name: 'Printer', job_ref: null,
      created_at: '2026-09-19T10:00:00Z',
      meta: { reported_weight_g: 25, balance_accounting: balanceAccounting },
    }]);
    renderModal({});

    expect(await screen.findByText(key)).toBeInTheDocument();
    expect(screen.queryByText('spoolUsage.warnReported')).not.toBeInTheDocument();
  });

  it('labels an estimated printer report even when a device name is present', async () => {
    api.usage.mockResolvedValue([{
      id: 3, event_type: 'printer_report', delta_weight_g: 30,
      remaining_weight_g: 950, device_name: 'Printer', job_ref: 'job-3',
      created_at: '2026-09-19T10:00:00Z',
      meta: { consumption_kind: 'estimated', estimate_source: 'slicer_progress' },
    }]);
    renderModal({});

    expect(await screen.findByText('Printer · spoolUsage.source.estimateSlicerProgress')).toBeInTheDocument();
    expect(screen.getByText('≈−30 spoolUsage.grams')).toBeInTheDocument();
    expect(screen.getByText('spoolUsage.estimatedApplied')).toBeInTheDocument();
  });

  it.each([
    ['reverted', 10, { consumption_kind: 'estimated', estimate_source: 'slicer_gcode', reverted: true }],
    ['reconciliation', 10, {
      consumption_kind: 'estimated', estimate_source: 'slicer_gcode',
      balance_accounting: 'needs_reconciliation',
    }],
    ['already in balance with no applied delta', 0, {
      consumption_kind: 'estimated', estimate_source: 'slicer_gcode',
      balance_accounting: 'already_in_balance',
    }],
  ])('does not call an estimate applied when %s', async (_reason, delta, meta) => {
    api.usage.mockResolvedValue([{
      id: 6, event_type: 'printer_report', delta_weight_g: delta,
      remaining_weight_g: 1000 - delta, device_name: 'Printer', job_ref: 'job-6',
      created_at: '2026-09-19T10:00:00Z', meta,
    }]);
    renderModal({});

    await screen.findByText(/Printer · spoolUsage\.source\.estimateSlicerGcode/);
    expect(screen.queryByText('spoolUsage.estimatedApplied')).not.toBeInTheDocument();
  });

  it('labels opening balance separately without showing a drift warning', async () => {
    api.usage.mockResolvedValue([{
      id: 4, event_type: 'reconcile_adjust', delta_weight_g: 5,
      remaining_weight_g: 995, device_name: null, job_ref: null,
      created_at: '2026-09-19T10:00:00Z',
      meta: {
        reason: 'opening_balance',
        balance_observed_at: '2026-09-19T10:00:00Z',
        measured_remaining_g: 995,
      },
    }]);
    renderModal({});

    expect(await screen.findByText('spoolUsage.source.opening_balance')).toBeInTheDocument();
    expect(screen.queryByText('spoolUsage.driftUnder')).not.toBeInTheDocument();
    expect(screen.queryByText('spoolUsage.driftOver')).not.toBeInTheDocument();
  });
});
