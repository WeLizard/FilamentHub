import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { PhysicalPrinter, PrinterEconomics } from '../../api/client';
import { PrinterCostRow } from './PrinterCostRow';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) =>
      values ? `${key} ${Object.values(values).join(' ')}` : key,
  }),
}));

const printer = { id: 1, name: 'Workshop' } as unknown as PhysicalPrinter;

const economics = (rateSource: string, rate: number): PrinterEconomics => ({
  printer_id: 1,
  configured: rateSource === 'printer',
  purchase_cost: null,
  residual_value: null,
  useful_life_hours: null,
  average_power_watts: 350,
  power_hotend_w: null,
  power_bed_w: null,
  power_steppers_w: null,
  power_electronics_w: null,
  maintenance_cost_per_hour: null,
  machine_hour_rate: rate || null,
  economics_currency: 'RUB',
  calculator_currency: 'RUB',
  depreciation_per_hour: 0,
  electricity_per_hour: 2.1,
  maintenance_per_hour: 0,
  machine_cost_per_hour: 2.1,
  effective_machine_hour_rate: rate,
  rate_below_cost: false,
  calculator_printer_power_w: 350,
  calculator_printing_rate_per_hour: Math.max(0, rate - 2.1),
  calculator_amortization_rate_per_hour: 0,
  calculator_electricity_cost_per_kwh: 6,
  sources: { rate: rateSource },
});

const renderRow = (
  resolvedEconomics: PrinterEconomics,
  rateMissing = false,
  onFixRate = vi.fn(),
) => render(
  <PrinterCostRow
    printers={[printer]}
    selectedPrinterId={printer.id}
    onSelect={vi.fn()}
    economics={resolvedEconomics}
    currency="RUB"
    rateMissing={rateMissing}
    onFixRate={onFixRate}
  />,
);

describe('PrinterCostRow rate discoverability', () => {
  it.each([
    ['account', 'printerCost.originAccount'],
    ['orca', 'printerCost.originOrca'],
  ])('names the %s fallback that will be charged', (rateSource, originKey) => {
    const view = renderRow(economics(rateSource, 80));

    expect(view.container).toHaveTextContent('printerCost.rowFallbackRate');
    expect(view.container).toHaveTextContent(originKey);
    expect(screen.queryByText('printerCost.rateMissing')).not.toBeInTheDocument();
  });

  it('keeps a printer-owned rate distinct from fallbacks', () => {
    const view = renderRow(economics('printer', 45));

    expect(view.container).toHaveTextContent('printerCost.rowConfigured');
    expect(view.container).not.toHaveTextContent('printerCost.rowFallbackRate');
  });

  it('labels an account fallback with its resolved currency', () => {
    const view = renderRow({
      ...economics('account', 170),
      economics_currency: 'USD',
      calculator_currency: 'RUB',
    });

    expect(view.container).toHaveTextContent('₽');
    expect(view.container).not.toHaveTextContent('$');
  });

  it('explains a missing rate and offers one direct settings action', () => {
    const onFixRate = vi.fn();
    renderRow(economics('none', 0), true, onFixRate);

    expect(screen.getByText('printerCost.rateMissing')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'printerCost.rateMissingAction' }));
    expect(onFixRate).toHaveBeenCalledOnce();
  });

  it('names the cost floor when a chosen rate is below machine cost', () => {
    const view = renderRow({
      ...economics('printer', 5),
      machine_cost_per_hour: 20.26,
      rate_below_cost: true,
    });

    expect(view.container).toHaveTextContent('printerCost.rowCostFloor');
    expect(view.container).toHaveTextContent('20.26');
    expect(view.container).not.toHaveTextContent('printerCost.rowConfigured');
  });
});
