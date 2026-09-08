import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { PrinterEconomics } from '../../api/client';
import { PrinterCostForm } from './PrinterCostForm';

const apiMocks = vi.hoisted(() => ({
  economics: vi.fn(),
  economicsSuggestion: vi.fn(),
  applyEconomicsSuggestion: vi.fn(),
  updateEconomics: vi.fn(),
}));

vi.mock('../../api/client', () => ({
  physicalPrintersAPI: apiMocks,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../Toast', () => ({
  toast: { error: vi.fn() },
}));

const economics = (powerSource: 'platform_default' | 'catalog_estimate'): PrinterEconomics => ({
  printer_id: 7,
  configured: false,
  purchase_cost: null,
  residual_value: null,
  useful_life_hours: powerSource === 'catalog_estimate' ? 7000 : null,
  average_power_watts: powerSource === 'catalog_estimate' ? 320 : null,
  power_hotend_w: powerSource === 'catalog_estimate' ? 40 : null,
  power_bed_w: powerSource === 'catalog_estimate' ? 240 : null,
  power_steppers_w: powerSource === 'catalog_estimate' ? 20 : null,
  power_electronics_w: powerSource === 'catalog_estimate' ? 30 : null,
  maintenance_cost_per_hour: null,
  machine_hour_rate: null,
  economics_currency: null,
  calculator_currency: 'RUB',
  depreciation_per_hour: 0,
  electricity_per_hour: 2,
  maintenance_per_hour: 0,
  machine_cost_per_hour: 2,
  effective_machine_hour_rate: 100,
  rate_below_cost: false,
  calculator_printer_power_w: 320,
  calculator_printing_rate_per_hour: 98,
  calculator_amortization_rate_per_hour: 0,
  calculator_electricity_cost_per_kwh: 6,
  sources: { power: 'estimate', rate: 'account' },
  applied_sources: {
    currency: 'account_explicit',
    machine_hour_rate: 'account_explicit',
    electricity_cost_per_kwh: 'account_explicit',
    printer_power_w: powerSource,
    machine_wear_per_hour: 'platform_default',
    depreciation_per_hour: 'none',
    maintenance_per_hour: 'platform_default',
  },
  readiness: {
    version: 1,
    status: 'partial',
    money_currency: 'RUB',
    required_fields: [{
      key: 'printer_power_w',
      value: 320,
      source: powerSource,
      source_currency: null,
      usable: true,
      missing_reason: null,
    }],
    reasons: [powerSource === 'catalog_estimate' ? 'catalog_estimate_used' : 'platform_default_used'],
  },
});

describe('PrinterCostForm suggestion provenance', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.economics.mockResolvedValue(economics('platform_default'));
    apiMocks.economicsSuggestion.mockResolvedValue({
      printer_id: 7,
      confidence: 'model',
      model_name: 'P2S',
      average_power_watts: 320,
      power_hotend_w: 40,
      power_bed_w: 240,
      power_steppers_w: 20,
      power_electronics_w: 30,
      useful_life_hours: 7000,
      maintenance_cost_per_hour: 5,
    });
    apiMocks.applyEconomicsSuggestion.mockResolvedValue(economics('catalog_estimate'));
  });

  it('renders the server-returned catalog source after applying a suggestion', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <PrinterCostForm
          printerId={7}
          printerName="P2S"
          currency="RUB"
          fallback={{ purchaseCost: 0, lifeHours: 0, powerWatts: 0, maintenance: 0, rate: 100 }}
        />
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'printerCost.applySuggested' }));

    await waitFor(() => expect(apiMocks.applyEconomicsSuggestion).toHaveBeenCalledWith(7, {
      usage: 'regular',
      fields: [
        'average_power_watts',
        'power_hotend_w',
        'power_bed_w',
        'power_steppers_w',
        'power_electronics_w',
        'useful_life_hours',
      ],
    }));
    expect(await screen.findByText('printerCost.readiness.sources.catalog_estimate')).toBeInTheDocument();
  });
});
