import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { PhysicalPrinter } from '../../api/client';
import type { EconomicsReadiness, EconomicsReadinessStatus, EconomicsSource } from '../../types/api';
import { PrinterCostRow } from './PrinterCostRow';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) =>
      values ? `${key} ${Object.values(values).join(' ')}` : key,
  }),
}));

const printer = { id: 1, name: 'Workshop' } as unknown as PhysicalPrinter;

const readiness = (
  status: EconomicsReadinessStatus,
  source: EconomicsSource = 'printer_explicit',
): EconomicsReadiness => ({
  version: 1,
  status,
  money_currency: 'RUB',
  required_fields: [{
    key: 'machine_hour_rate',
    value: status === 'incomplete' ? null : 80,
    source: status === 'incomplete' ? 'none' : source,
    source_currency: 'RUB',
    usable: status !== 'incomplete',
    missing_reason: status === 'incomplete' ? 'missing' : null,
  }],
  reasons: status === 'configured' ? [] : [
    status === 'partial' ? 'incomplete_pair' : 'missing',
  ],
});

const renderRow = (
  entries = [{ id: 'printer-1', label: 'Workshop', readiness: readiness('configured') }],
  onFixRate = vi.fn(),
) => render(
  <PrinterCostRow
    printers={[printer]}
    selectedPrinterId={printer.id}
    onSelect={vi.fn()}
    readinessEntries={entries}
    onFixRate={onFixRate}
  />,
);

describe('PrinterCostRow economics readiness', () => {
  it('shows a configured state before calculation', () => {
    renderRow();

    expect(screen.getByText('printerCost.readiness.status.configured.title')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'printerCost.readiness.configure' })).not.toBeInTheDocument();
  });

  it('never presents a filled catalog estimate as a problem', () => {
    const contract = readiness('configured', 'catalog_estimate');
    contract.reasons = ['catalog_estimate_used', 'platform_default_used', 'provenance_unknown'];
    const view = renderRow([{ id: 'printer-1', label: 'Workshop', readiness: contract }]);

    expect(screen.getByText('printerCost.readiness.status.configured.title')).toBeInTheDocument();
    expect(view.container.textContent).not.toContain('catalog_estimate');
  });

  it('lists a real problem but drops provenance notes beside it', () => {
    const contract = readiness('partial');
    contract.reasons = ['catalog_estimate_used', 'incomplete_pair'];
    const view = renderRow([{ id: 'printer-1', label: 'Workshop', readiness: contract }]);

    expect(screen.getByText('printerCost.readiness.reasons.incomplete_pair')).toBeInTheDocument();
    expect(view.container.textContent).not.toContain('catalog_estimate_used');
  });

  it('names the missing field once, without a separate reason line', () => {
    const view = renderRow([{ id: 'printer-1', label: 'Workshop', readiness: readiness('incomplete') }]);

    expect(screen.getByText('printerCost.readiness.fields.machine_hour_rate')).toBeInTheDocument();
    expect(view.container.textContent).not.toContain('printerCost.readiness.reasons.missing');
  });

  it('offers one natural-width action for incomplete economics', () => {
    const onFixRate = vi.fn();
    renderRow([{ id: 'printer-1', label: 'Workshop', readiness: readiness('incomplete') }], onFixRate);

    const action = screen.getByRole('button', { name: 'printerCost.readiness.configure' });
    expect(action).not.toHaveClass('w-full');
    fireEvent.click(action);
    expect(onFixRate).toHaveBeenCalledOnce();
  });

  it('names each affected printer in a mixed batch and uses the worst state', () => {
    renderRow([
      { id: 'printer-1', label: 'Workshop', readiness: readiness('partial') },
      { id: 'printer-2', label: 'Backup', readiness: readiness('incomplete') },
    ]);

    expect(screen.getByText('printerCost.readiness.status.incomplete.title')).toBeInTheDocument();
    expect(screen.getByText(/Workshop:/)).toBeInTheDocument();
    expect(screen.getByText(/Backup:/)).toBeInTheDocument();
  });

  it('keeps a load failure visible', () => {
    render(
      <PrinterCostRow
        printers={[printer]}
        selectedPrinterId={printer.id}
        onSelect={vi.fn()}
        readinessEntries={[]}
        readinessError
        onFixRate={vi.fn()}
      />,
    );

    expect(screen.getByText('printerCost.readiness.unavailable')).toBeInTheDocument();
  });
});
