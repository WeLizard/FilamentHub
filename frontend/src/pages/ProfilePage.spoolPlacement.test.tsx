import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  assignMaterialSlot: vi.fn(),
  createSpool: vi.fn(),
  updateSpool: vi.fn(),
  listPresets: vi.fn(),
  listPrinters: vi.fn(),
  toastSuccess: vi.fn(),
}));

vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../contexts/AuthContext', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../contexts/AuthContext')>()),
  useAuth: () => ({ user: { id: 1 } }),
}));

vi.mock('../hooks/useUserCurrency', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/useUserCurrency')>()),
  useUserCurrency: () => ({ currency: 'RUB' }),
}));

vi.mock('../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/client')>();
  return {
    ...original,
    physicalPrintersAPI: {
      ...original.physicalPrintersAPI,
      list: apiMocks.listPrinters,
    },
    presetsAPI: {
      ...original.presetsAPI,
      list: apiMocks.listPresets,
    },
    spoolsAPI: {
      ...original.spoolsAPI,
      create: apiMocks.createSpool,
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

import { SpoolForm } from './ProfilePage';

describe('SpoolForm printer placement', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

    await waitFor(() => expect(apiMocks.updateSpool).toHaveBeenLastCalledWith(1270, {
      initial_weight_g: 900,
      used_weight_g: 5,
      expected_initial_weight_g: 1000,
      expected_used_weight_g: 5,
    }));
  });
});
