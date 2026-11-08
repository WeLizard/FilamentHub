import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { currencySymbol } from '../utils/currency';

const apiMocks = vi.hoisted(() => ({
  assignMaterialSlot: vi.fn(),
  createSpool: vi.fn(),
  createBatch: vi.fn(),
  batchLimit: vi.fn(),
  listCurrencies: vi.fn(),
  updateSpool: vi.fn(),
  listPresets: vi.fn(),
  getFilament: vi.fn(),
  listPrinters: vi.fn(),
  toastSuccess: vi.fn(),
  currency: 'RUB',
}));

vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) => key.startsWith('profilePage.spoolAddModal.preview')
      ? `${key} ${JSON.stringify(values)}`
      : key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('../contexts/AuthContext', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../contexts/AuthContext')>()),
  useAuth: () => ({ user: { id: 1 } }),
}));

vi.mock('../hooks/useUserCurrency', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/useUserCurrency')>()),
  useUserCurrency: () => ({ currency: apiMocks.currency }),
}));

vi.mock('../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/client')>();
  return {
    ...original,
    currenciesAPI: { list: apiMocks.listCurrencies },
    physicalPrintersAPI: {
      ...original.physicalPrintersAPI,
      list: apiMocks.listPrinters,
    },
    filamentsAPI: {
      ...original.filamentsAPI,
      get: apiMocks.getFilament,
    },
    presetsAPI: {
      ...original.presetsAPI,
      list: apiMocks.listPresets,
    },
    spoolsAPI: {
      ...original.spoolsAPI,
      create: apiMocks.createSpool,
      createBatch: apiMocks.createBatch,
      batchLimit: apiMocks.batchLimit,
      update: apiMocks.updateSpool,
    },
  };
});

vi.mock('../components/presetSlots/assignmentDelivery', async (importOriginal) => ({
  ...(await importOriginal<
    typeof import('../components/presetSlots/assignmentDelivery')
  >()),
  assignMaterialSlot: apiMocks.assignMaterialSlot,
  assignmentDeliveryNotice: () => ({
    tone: 'success',
    key: 'presetSlots.delivery.delivered',
  }),
}));

vi.mock('../components/Toast', () => ({
  toast: {
    error: vi.fn(),
    info: vi.fn(),
    success: apiMocks.toastSuccess,
    warning: vi.fn(),
  },
}));

import { SpoolCard, SpoolForm } from './ProfilePage';

describe('SpoolForm printer placement', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    apiMocks.currency = 'RUB';
    apiMocks.listCurrencies.mockResolvedValue([
      { code: 'RUB', symbol: '₽', decimals: 2, rounding_step: 10, countries: ['RU'] },
      { code: 'EUR', symbol: '€', decimals: 2, rounding_step: 1, countries: ['DE'] },
      { code: 'IRR', symbol: '﷼', decimals: 2, rounding_step: 50000, countries: ['IR'] },
      { code: 'JPY', symbol: '¥', decimals: 0, rounding_step: 50, countries: ['JP'] },
    ]);
    apiMocks.batchLimit.mockResolvedValue({ limit: 100 });
    apiMocks.createBatch.mockResolvedValue({});
    apiMocks.listPresets.mockResolvedValue({ items: [] });
    apiMocks.listPrinters.mockResolvedValue([
      {
        id: 948,
        logical_id: 'printer-948',
        printer_id: null,
        name: 'Bambu Lab P1S',
        printer_profile_ids: [],
        material_systems: [
          {
            id: 119,
            name: 'AMS 1',
            kind: 'ams',
            provider: 'bambu',
            capabilities: ['read', 'write'],
            active: true,
            declared_slot_count: 4,
            slots: [
              {
                id: 5757,
                provider_index: 0,
                label: 'AMS 1 · 1',
                kind: 'gate',
                active: true,
                assignment_revision: 0,
                assignment: null,
                legacy_projection: null,
              },
              {
                id: 5760,
                provider_index: 3,
                label: 'AMS 1 · 4',
                kind: 'gate',
                active: true,
                assignment_revision: 7,
                assignment: null,
                legacy_projection: null,
              },
            ],
          },
        ],
        connectors: [],
        has_api_key: false,
        printer_hostname: null,
        reports_feed: true,
        last_seen_at: null,
        created_at: '2026-09-05T12:00:00Z',
        updated_at: '2026-09-05T12:00:00Z',
      },
    ]);
    apiMocks.createSpool.mockResolvedValue({
      id: 1270,
      user_id: 1,
      filament_id: null,
      filament: null,
      initial_weight_g: 1000,
      used_weight_g: 0,
      remaining_weight_g: 1000,
      remaining_pct: 100,
      price: null,
      currency: null,
      state: 'shelf',
      source: 'manual',
      lot_nr: null,
      comment: null,
      created_at: '2026-09-05T12:00:00Z',
      updated_at: '2026-09-05T12:00:00Z',
      last_used_at: null,
      extra: null,
    });
    apiMocks.updateSpool.mockResolvedValue({});
    apiMocks.assignMaterialSlot.mockResolvedValue({ status: 'delivered' });
  });

  it('shows the canonical Bambu label and assigns its exact material slot', async () => {
    const renderForm = () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      });
      return render(
        <QueryClientProvider client={queryClient}>
          <SpoolForm
            mode="create"
            initialPlacement="printer"
            onSaved={vi.fn()}
            onCancel={vi.fn()}
          />
        </QueryClientProvider>,
      );
    };

    const firstRun = renderForm();

    await waitFor(() => expect(apiMocks.listPrinters).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', {
      name: 'profilePage.spoolAddModal.submit',
    }));

    const fourthAmsSlot = await screen.findByRole('button', { name: 'AMS 1 · 4' });
    expect(screen.queryByRole('button', { name: '3' })).not.toBeInTheDocument();
    fireEvent.click(fourthAmsSlot);
    fireEvent.click(screen.getByRole('button', {
      name: 'profilePage.spoolGateStep.assign',
    }));

    await waitFor(() => {
      expect(apiMocks.assignMaterialSlot).toHaveBeenCalledWith(948, 119, 5760, {
        expected_revision: 7,
        expected_spool_id: null,
        spool_id: 1270,
      });
    });
    await waitFor(() => expect(apiMocks.toastSuccess).toHaveBeenCalledTimes(1));
    firstRun.unmount();

    renderForm();
    fireEvent.click(await screen.findByRole('button', {
      name: 'profilePage.spoolAddModal.submit',
    }));
    fireEvent.click(await screen.findByRole('button', { name: 'AMS 1 · 4' }));
    fireEvent.click(screen.getByRole('button', {
      name: 'profilePage.spoolGateStep.assign',
    }));
    await waitFor(() => expect(apiMocks.assignMaterialSlot).toHaveBeenCalledTimes(2));
    expect(apiMocks.toastSuccess).toHaveBeenCalledTimes(2);
    expect(apiMocks.toastSuccess).toHaveBeenLastCalledWith(
      'presetSlots.delivery.delivered',
      undefined,
      'preset-slot-assignment-delivery',
    );
  });

  it('edits only changed fields and guards an intentional weight edit', async () => {
    const spool = {
      id: 1270,
      user_id: 1,
      filament_id: 44,
      filament: null,
      initial_weight_g: 1000,
      used_weight_g: 5,
      remaining_weight_g: 995,
      remaining_pct: 99.5,
      price: 20,
      currency: 'RUB',
      state: 'active' as const,
      source: 'manual',
      lot_nr: 'LOT-1',
      comment: 'old comment',
      created_at: '2026-09-05T12:00:00Z',
      updated_at: '2026-09-05T12:00:00Z',
      last_used_at: null,
      extra: null,
    };

    const view = render(
      <QueryClientProvider client={new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })}>
        <SpoolForm mode="edit" spool={spool} onSaved={vi.fn()} onCancel={vi.fn()} />
      </QueryClientProvider>,
    );

    fireEvent.change(screen.getByDisplayValue('old comment'), {
      target: { value: 'new comment' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'profilePage.spoolEditModal.submit' }));

    await waitFor(() => expect(apiMocks.updateSpool).toHaveBeenCalledWith(1270, {
      comment: 'new comment',
    }));

    view.rerender(
      <QueryClientProvider client={new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })}>
        <SpoolForm
          mode="edit"
          spool={{ ...spool, comment: 'new comment' }}
          onSaved={vi.fn()}
          onCancel={vi.fn()}
        />
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByDisplayValue('1000'), { target: { value: '900' } });
    fireEvent.click(screen.getByRole('button', { name: 'profilePage.spoolEditModal.submit' }));

    // A label-weight edit is not a balance check: the used amount stays out of it.
    await waitFor(() => expect(apiMocks.updateSpool).toHaveBeenLastCalledWith(1270, {
      initial_weight_g: 900,
      expected_initial_weight_g: 1000,
    }));

    view.unmount();
    render(
      <QueryClientProvider client={new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })}>
        <SpoolForm mode="edit" spool={spool} onSaved={vi.fn()} onCancel={vi.fn()} />
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByDisplayValue('5'), { target: { value: '8' } });
    fireEvent.click(screen.getByRole('button', { name: 'profilePage.spoolEditModal.submit' }));

    await waitFor(() => expect(apiMocks.updateSpool).toHaveBeenLastCalledWith(1270, {
      used_weight_g: 8,
      expected_initial_weight_g: 1000,
      expected_used_weight_g: 5,
    }));
  });

  it.each([
    { currency: 'RUB', price: '12.34', step: '0.01', totalShares: '4.12 ₽ × 1, 4.11 ₽ × 2' },
    { currency: 'EUR', price: '12.34', step: '0.01', totalShares: '4.12 € × 1, 4.11 € × 2' },
    { currency: 'IRR', price: '12.34', step: '0.01', totalShares: '4.12 ﷼ × 1, 4.11 ﷼ × 2' },
    { currency: 'JPY', price: '12.34', step: '1', totalShares: null },
    { currency: 'KWD', price: '12.345', step: 'any', totalShares: null },
    { currency: 'RUB', price: '12.3456', step: '0.01', totalShares: null },
  ])('preserves $currency $price in single/edit/per-spool and validates total currency precision', async ({ currency, price, step, totalShares }) => {
    apiMocks.currency = currency;
    const saved = {
      ...await apiMocks.createSpool(),
      price: 10,
      currency,
    };
    apiMocks.createSpool.mockClear();

    for (const flow of ['create', 'edit', 'per_spool', 'total'] as const) {
      apiMocks.createBatch.mockClear();
      const mode = flow === 'edit' ? 'edit' : 'create';
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const view = render(
        <QueryClientProvider client={queryClient}>
          <SpoolForm mode={mode} spool={mode === 'edit' ? saved : undefined}
            initialPlacement="shelf" onSaved={vi.fn()} onCancel={vi.fn()} />
        </QueryClientProvider>,
      );
      if (flow === 'per_spool' || flow === 'total') {
        fireEvent.change(view.container.querySelector('input[max]')!, { target: { value: '3' } });
        fireEvent.click(screen.getByRole('button', {
          name: `profilePage.spoolAddModal.${flow === 'total' ? 'priceTotal' : 'pricePerSpool'}`,
        }));
      }
      const input = screen.getByPlaceholderText('profilePage.spoolAddModal.pricePlaceholder') as HTMLInputElement;
      fireEvent.change(input, { target: { value: price } });
      if (flow === 'per_spool') {
        const preview = screen.getByText(/profilePage.spoolAddModal.previewPerSpool/);
        expect(preview).toHaveTextContent(`"price":"${price} ${currencySymbol(currency)}"`);
        const total = (Number(price) * 3).toFixed(4).replace(/0+$/, '');
        expect(preview).toHaveTextContent(`"total":"${total} ${currencySymbol(currency)}"`);
      }
      if (flow === 'total') {
        await waitFor(() => expect(queryClient.getQueryData(['currencies'])).toBeDefined());
        await waitFor(() => expect(input).toHaveAttribute('step', step));
        if (totalShares) {
          expect(screen.getByText(/profilePage.spoolAddModal.previewTotal/)).toHaveTextContent(totalShares);
        }
      }
      if (flow === 'total' && step === 'any') {
        expect(screen.queryByText(/apiErrors.ERR_SPOOL_BATCH_PRICE_PRECISION/)).not.toBeInTheDocument();
        expect(screen.queryByText(/profilePage.spoolAddModal.previewTotal/)).not.toBeInTheDocument();
      }
      if (flow === 'total' && step !== 'any' && !totalShares) {
        expect(input.validity.stepMismatch).toBe(true);
        expect(input.form!.checkValidity()).toBe(false);
        expect(screen.getByText(/apiErrors.ERR_SPOOL_BATCH_PRICE_PRECISION/)).toBeInTheDocument();
        expect(screen.queryByText(/profilePage.spoolAddModal.previewTotal/)).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'profilePage.spoolAddModal.submit' }));
        expect(apiMocks.createBatch).not.toHaveBeenCalled();
        view.unmount();
        continue;
      }
      // A direct submit event bypasses native constraints and missed the original step=1 regression.
      expect(input.validity.stepMismatch).toBe(false);
      expect(input.form!.checkValidity()).toBe(true);
      fireEvent.click(screen.getByRole('button', { name: `profilePage.spool${mode === 'edit' ? 'Edit' : 'Add'}Modal.submit` }));

      const expected = { price: Number(price), currency };
      if (flow === 'edit') {
        await waitFor(() => expect(apiMocks.updateSpool).toHaveBeenCalledWith(saved.id, expected));
      } else if (flow === 'create') {
        await waitFor(() => expect(apiMocks.createSpool).toHaveBeenCalledWith(expect.objectContaining(expected)));
      } else {
        await waitFor(() => expect(apiMocks.createBatch).toHaveBeenCalledWith(expect.objectContaining({
          ...expected, quantity: 3, price_mode: flow,
        })));
      }
      view.unmount();
    }

    render(
      <QueryClientProvider client={new QueryClient()}>
        <SpoolCard spool={{ ...saved, price: Number(price) }} onEdit={vi.fn()}
          onUse={vi.fn()} onDelete={vi.fn()} onStateChange={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(screen.getByText(`${price} ${currencySymbol(currency)}`)).toBeInTheDocument();
  });

  it.each(['', '0', '-0.01'])('keeps empty, zero and negative price constraints (%s)', async (price) => {
    const view = render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <SpoolForm mode="create" initialPlacement="shelf" onSaved={vi.fn()} onCancel={vi.fn()} />
      </QueryClientProvider>,
    );
    const input = screen.getByPlaceholderText('profilePage.spoolAddModal.pricePlaceholder') as HTMLInputElement;
    fireEvent.change(input, { target: { value: price } });
    expect(input.form!.checkValidity()).toBe(price !== '-0.01');
    fireEvent.click(screen.getByRole('button', { name: 'profilePage.spoolAddModal.submit' }));
    if (price === '-0.01') {
      expect(apiMocks.createSpool).not.toHaveBeenCalled();
    } else {
      await waitFor(() => expect(apiMocks.createSpool).toHaveBeenCalledWith(expect.objectContaining({
        price: price === '' ? null : 0,
        currency: price === '' ? null : 'RUB',
      })));
    }
    view.unmount();
  });

  it('groups the filament picker under alphabetical brand headings with brandless last', async () => {
    const filaments: Record<number, { brand_name: string | null; name: string }> = {
      1: { brand_name: 'Polymaker', name: 'PLA Pro' },
      2: { brand_name: 'eSUN', name: 'PETG' },
      3: { brand_name: null, name: 'Mystery PLA' },
      4: { brand_name: 'eSUN', name: 'ABS' },
    };
    apiMocks.listPresets.mockResolvedValue({
      items: Object.keys(filaments).map((id) => ({ filament_id: Number(id) })),
    });
    apiMocks.getFilament.mockImplementation(async (id: number) => ({
      id,
      color_name: null,
      ...filaments[id],
    }));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <SpoolForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />
      </QueryClientProvider>,
    );

    const picker = screen.getByPlaceholderText('profilePage.spoolAddModal.filamentPlaceholder');
    await waitFor(() => expect(apiMocks.getFilament).toHaveBeenCalledTimes(4));
    fireEvent.focus(picker);
    await screen.findByRole('button', { name: 'PETG' });

    const listText = screen.getByRole('button', { name: 'PETG' }).closest('.scrollbar-contained')!;
    expect(
      Array.from(listText.children).map((row) => row.textContent),
    ).toEqual([
      'eSUNABS',
      'PETG',
      'PolymakerPLA Pro',
      'profilePage.spoolAddModal.otherBrandMystery PLA',
    ]);
  });
});
