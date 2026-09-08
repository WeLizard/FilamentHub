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
    status === 'partial' ? 'catalog_estimate_used' : 'missing',
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

  it('uses the exhaustive source label in readiness details', () => {
    renderRow([{ id: 'printer-1', label: 'Workshop', readiness: readiness('partial', 'catalog_estimate') }]);

    fireEvent.click(screen.getByText('printerCost.readiness.sourcesTitle'));
    expect(screen.getByText('printerCost.readiness.sources.catalog_estimate')).toBeInTheDocument();
    expect(screen.getByText('printerCost.readiness.reasons.catalog_estimate_used')).toBeInTheDocument();
  });

  it('shows mixed resolved sources without assigning them to individual editor inputs', () => {
    const contract = readiness('partial', 'account_explicit');
    contract.required_fields.push({
      key: 'printer_power_w',
      value: 320,
      source: 'catalog_estimate',
      source_currency: null,
      usable: true,
      missing_reason: null,
    });
    renderRow([{ id: 'printer-1', label: 'Workshop', readiness: contract }]);

    fireEvent.click(screen.getByText('printerCost.readiness.sourcesTitle'));
    expect(screen.getByText('printerCost.readiness.sources.account_explicit')).toBeInTheDocument();
    expect(screen.getByText('printerCost.readiness.sources.catalog_estimate')).toBeInTheDocument();
  });

  it('offers one natural-width action for incomplete economics', () => {
    const onFixRate = vi.fn();
    renderRow([{ id: 'printer-1', label: 'Workshop', readiness: readiness('incomplete') }], onFixRate);

    const action = screen.getByRole('button', { name: 'printerCost.readiness.configure' });
    expect(action).not.toHaveClass('w-full');
    fireEvent.click(action);
    expect(onFixRate).toHaveBeenCalledOnce();
  });

  it('explains a contract-level incomplete pair', () => {
    const contract = readiness('partial');
    contract.reasons = ['incomplete_pair'];
    renderRow([{ id: 'printer-1', label: 'Workshop', readiness: contract }]);

    fireEvent.click(screen.getByText('printerCost.readiness.sourcesTitle'));
    expect(screen.getByText('printerCost.readiness.reasons.incomplete_pair')).toBeInTheDocument();
  });

  it('does not repeat a contract reason already shown on its field', () => {
    const view = renderRow([{
      id: 'printer-1',
      label: 'Workshop',
      readiness: readiness('incomplete'),
    }]);

    fireEvent.click(screen.getByText('printerCost.readiness.sourcesTitle'));
    const text = view.container.textContent ?? '';
    expect(text.split('printerCost.readiness.reasons.missing')).toHaveLength(2);
    expect(screen.queryByText('printerCost.readiness.reasonsTitle')).not.toBeInTheDocument();
  });

  it('names every affected printer in a mixed batch and uses the worst state', () => {
    renderRow([
      { id: 'printer-1', label: 'Workshop', readiness: readiness('partial') },
      { id: 'printer-2', label: 'Backup', readiness: readiness('incomplete') },
    ]);

    expect(screen.getByText('printerCost.readiness.status.incomplete.title')).toBeInTheDocument();
    expect(screen.getByText(/Workshop, Backup/)).toBeInTheDocument();
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
