import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { PhysicalPrinter, QrScanResponse, UserSpool } from '../api/client';
import { QrScanResultModal } from './QrScanResultModal';

const { listPrinters, listSpools, savePreset } = vi.hoisted(() => ({
  listPrinters: vi.fn(),
  listSpools: vi.fn(),
  savePreset: vi.fn(),
}));

const { recommendationState } = vi.hoisted(() => ({
  recommendationState: {
    current: {
      options: [],
      selectedKey: '',
      select: vi.fn(),
      recommendation: null,
      printerName: null,
      isLoadingOptions: false,
      isOptionsError: false,
      isLoadingRecommendation: false,
      isRecommendationError: false,
    } as any,
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string | number>) =>
      key === 'qrScanResult.inventoryLocationPrinter'
        ? `${key}:${values?.printer}:${values?.slot}`
        : key,
  }),
}));

vi.mock('../api/client', () => ({
  physicalPrintersAPI: { list: listPrinters },
  savedPresetsAPI: { save: savePreset },
  spoolsAPI: { listForFilament: listSpools },
}));

vi.mock('../hooks/useConfigurationPresetRecommendation', () => ({
  useConfigurationPresetRecommendation: () => recommendationState.current,
}));

const baseResult = {
  filament: {
    id: 42,
    brand_name: 'QR Brand',
    name: 'Exact PLA',
    color_name: 'Signal Blue',
    material_type: 'PLA',
  },
  preset_added: false,
  preset: { id: 77, name: 'Official Exact PLA' },
  preset_type: 'official',
  preset_saved: false,
  preset_sync_enabled: null,
} as QrScanResponse;

const makeSpool = (overrides: Partial<UserSpool> = {}): UserSpool => ({
  id: 11,
  user_id: 15,
  filament_id: 42,
  filament: null,
  initial_weight_g: 1000,
  used_weight_g: 250,
  remaining_weight_g: 750,
  remaining_pct: 75,
  price: null,
  currency: null,
  state: 'shelf',
  source: 'manual',
  lot_nr: null,
  comment: null,
  created_at: '2026-08-26T08:00:00Z',
  updated_at: '2026-08-26T08:00:00Z',
  last_used_at: null,
  extra: null,
  ...overrides,
});

function renderModal(
  result: QrScanResponse,
  options: {
    userId?: number | null;
    onRequestLogin?: () => void;
    onAddSpool?: (placement: 'shelf' | 'printer') => void;
    onOpenSpools?: () => void;
  } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <QrScanResultModal
        result={result}
        userId={options.userId === undefined ? 15 : options.userId}
        onClose={vi.fn()}
        onRequestLogin={options.onRequestLogin}
        onAddSpool={options.onAddSpool}
        onOpenSpools={options.onOpenSpools}
      />
    </QueryClientProvider>,
  );
}

describe('QrScanResultModal', () => {
  beforeEach(() => {
    recommendationState.current = {
      options: [],
      selectedKey: '',
      select: vi.fn(),
      recommendation: null,
      printerName: null,
      isLoadingOptions: false,
      isOptionsError: false,
      isLoadingRecommendation: false,
      isRecommendationError: false,
    };
    listPrinters.mockReset();
    listPrinters.mockResolvedValue([]);
    listSpools.mockReset();
    listSpools.mockResolvedValue([]);
    savePreset.mockReset();
  });

  it('saves only after an explicit click and keeps Orca sync disabled', async () => {
    savePreset.mockResolvedValueOnce({ preset_id: 77, sync: false });
    renderModal(baseResult);

    expect(savePreset).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'qrScanResult.savePreset' }));

    await waitFor(() => expect(savePreset).toHaveBeenCalledWith(77, false));
    expect(await screen.findByText('qrScanResult.presetSaved')).toBeInTheDocument();
    expect(screen.getByText('qrScanResult.syncOff')).toBeInTheDocument();
  });

  it('keeps the explicit save available when saving fails', async () => {
    savePreset.mockRejectedValueOnce(new Error('network unavailable'));
    renderModal(baseResult);

    fireEvent.click(screen.getByRole('button', { name: 'qrScanResult.savePreset' }));

    expect(await screen.findByText('qrScanResult.saveError')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'qrScanResult.savePreset' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('qrScanResult.presetSaved')).not.toBeInTheDocument();
  });

  it('reports an existing synced preset without offering another save', () => {
    renderModal({
      ...baseResult,
      preset_saved: true,
      preset_sync_enabled: true,
    });

    expect(screen.getByText('qrScanResult.presetSaved')).toBeInTheDocument();
    expect(screen.getByText('qrScanResult.syncOn')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'qrScanResult.savePreset' }),
    ).not.toBeInTheDocument();
    expect(savePreset).not.toHaveBeenCalled();
  });

  it('shows preset provenance without redundant scan headings', () => {
    renderModal(baseResult);

    expect(screen.getByText('qrScanResult.presetSourceOfficial')).toBeInTheDocument();
    expect(screen.queryByText('qrScanResult.title')).not.toBeInTheDocument();
    expect(screen.queryByText('qrScanResult.recognized')).not.toBeInTheDocument();
    expect(screen.queryByText('qrScanResult.exactVariant')).not.toBeInTheDocument();
  });

  it('labels a community fallback honestly', () => {
    renderModal({
      ...baseResult,
      preset: { ...baseResult.preset!, is_official: false },
      preset_type: 'community',
    });

    expect(screen.getByText('qrScanResult.presetSourceCommunity')).toBeInTheDocument();
    expect(screen.getByText('Official Exact PLA')).toBeInTheDocument();
  });

  it('saves the configuration recommendation rather than the generic scan preset', async () => {
    recommendationState.current = {
      ...recommendationState.current,
      selectedKey: '31:91',
      printerName: 'Configured Voron',
      recommendation: {
        preset: {
          ...baseResult.preset,
          id: 88,
          name: 'Compatible community preset',
          is_official: false,
        },
        ranking_base_score: 1,
        ranking_score: 1.1,
        ranking_bonuses: [{ kind: 'rating', value: 0.1 }],
        match_score: 1.1,
        match_reason: 'exact_match',
        compatibility_status: 'compatible',
        technical_match: 1,
        evidence_coverage: 1,
        evidence_count: 1,
        evidence_total: 1,
        compatibility_coverage: 1,
        compatibility_checks: [{
          kind: 'hotend_temperature',
          status: 'compatible',
          required_values: [220],
          available_values: [300],
          required_value: 220,
          available_value: 300,
          unit: '°C',
          requirement_source: 'preset',
          capability_source: 'catalog_printer',
        }],
        hard_conflicts: [],
        saved: false,
        sync_enabled: null,
      },
    };
    savePreset.mockResolvedValueOnce({ preset_id: 88, sync: false });

    renderModal(baseResult);

    expect(screen.getByText('Compatible community preset')).toBeInTheDocument();
    expect(screen.getByText('qrScanResult.presetSourceCommunity')).toBeInTheDocument();
    expect(
      screen.getByText('profilePage.calculator.printerCompatibilityStatus.compatible'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('profilePage.calculator.printerCompatibilityTechnicalSummary'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('profilePage.calculator.printerCompatibilitySources'),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'qrScanResult.savePreset' }));
    await waitFor(() => expect(savePreset).toHaveBeenCalledWith(88, false));
  });

  it('does not offer another save for an already saved recommendation', () => {
    recommendationState.current = {
      ...recommendationState.current,
      selectedKey: '31:91',
      printerName: 'Configured Voron',
      recommendation: {
        preset: { ...baseResult.preset, id: 89, name: 'Already saved' },
        ranking_base_score: 1,
        ranking_score: 1.05,
        ranking_bonuses: [{ kind: 'official', value: 0.05 }],
        match_score: 1.05,
        match_reason: 'exact_match',
        compatibility_status: 'unknown',
        technical_match: null,
        evidence_coverage: 0,
        evidence_count: 0,
        evidence_total: 0,
        compatibility_coverage: 0,
        compatibility_checks: [],
        hard_conflicts: [],
        saved: true,
        sync_enabled: false,
      },
    };

    renderModal(baseResult);

    expect(screen.getByText('qrScanResult.presetSaved')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'qrScanResult.savePreset' })).not.toBeInTheDocument();
    expect(savePreset).not.toHaveBeenCalled();
  });

  it('keeps anonymous recognition read-only and offers sign-in', () => {
    const onRequestLogin = vi.fn();
    renderModal(
      {
        ...baseResult,
        preset_saved: null,
        preset_sync_enabled: null,
      },
      { userId: null, onRequestLogin },
    );

    expect(screen.getByText('qrScanResult.loginHint')).toBeInTheDocument();
    expect(screen.getByText('qrScanResult.inventoryLoginHint')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'qrScanResult.savePreset' }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'qrScanResult.login' }));
    expect(onRequestLogin).toHaveBeenCalledTimes(1);
    expect(listPrinters).not.toHaveBeenCalled();
    expect(listSpools).not.toHaveBeenCalled();
    expect(savePreset).not.toHaveBeenCalled();
  });

  it('does not invent a preset when the catalog has none', () => {
    renderModal({
      ...baseResult,
      preset: null,
      preset_saved: null,
      preset_sync_enabled: null,
    });

    expect(screen.getByText('qrScanResult.noPreset')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'qrScanResult.savePreset' }),
    ).not.toBeInTheDocument();
  });

  it('shows that no exact user spool exists without changing recognition', async () => {
    const onAddSpool = vi.fn();
    renderModal(baseResult, { onAddSpool });

    expect(await screen.findByText('qrScanResult.inventoryNone')).toBeInTheDocument();
    expect(listSpools).toHaveBeenCalledWith(42);
    fireEvent.click(screen.getByRole('button', { name: 'qrScanResult.addToShelf' }));
    expect(onAddSpool).toHaveBeenCalledWith('shelf');
    fireEvent.click(
      screen.getByRole('button', { name: 'qrScanResult.installInPrinter' }),
    );
    expect(onAddSpool).toHaveBeenCalledWith('printer');
  });

  it('shows one exact available spool and ignores a different variant', async () => {
    const onAddSpool = vi.fn();
    listSpools.mockResolvedValueOnce([
      makeSpool(),
      makeSpool({ id: 12, filament_id: 99 }),
    ]);
    renderModal(baseResult, { onAddSpool });

    expect(await screen.findByText('qrScanResult.inventoryOne')).toBeInTheDocument();
    expect(screen.getByTestId('qr-inventory-spool-11')).toBeInTheDocument();
    expect(screen.queryByTestId('qr-inventory-spool-12')).not.toBeInTheDocument();
    expect(screen.getByText('profilePage.spoolState.shelf')).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', { name: 'qrScanResult.addToShelf' }),
    );
    expect(onAddSpool).toHaveBeenCalledWith('shelf');
  });

  it('summarizes multiple available, archived and empty spools', async () => {
    const onOpenSpools = vi.fn();
    const onAddSpool = vi.fn();
    listPrinters.mockResolvedValueOnce([
      {
        id: 31,
        name: 'Canonical Printer',
        material_systems: [
          {
            id: 41,
            active: true,
            slots: [
              {
                id: 51,
                provider_index: 2,
                label: 'AMS A3',
                active: true,
                assignment: {
                  id: 61,
                  spool_id: 21,
                  active: true,
                },
              },
            ],
          },
        ],
      } as PhysicalPrinter,
    ]);
    listSpools.mockResolvedValueOnce([
      makeSpool({
        id: 21,
        state: 'active',
        extra: {
          printer_name: JSON.stringify('Stale Printer'),
          mmu_gate_map: JSON.stringify(1),
        },
      }),
      makeSpool({ id: 22 }),
      makeSpool({ id: 23, remaining_weight_g: 500 }),
      makeSpool({ id: 24, remaining_weight_g: 300 }),
      makeSpool({ id: 25, state: 'archived' }),
      makeSpool({ id: 26, state: 'empty', remaining_weight_g: 0 }),
    ]);
    renderModal(baseResult, { onAddSpool, onOpenSpools });

    expect(await screen.findByText('qrScanResult.inventoryMany')).toBeInTheDocument();
    expect(screen.getByTestId('qr-inventory-spool-21')).toBeInTheDocument();
    expect(screen.getByTestId('qr-inventory-spool-22')).toBeInTheDocument();
    expect(screen.getByTestId('qr-inventory-spool-23')).toBeInTheDocument();
    expect(screen.queryByTestId('qr-inventory-spool-24')).not.toBeInTheDocument();
    expect(
      screen.getByText(
        'qrScanResult.inventoryLocationPrinter:Canonical Printer:AMS A3',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('qrScanResult.inventoryArchived')).toBeInTheDocument();
    expect(screen.getByText('qrScanResult.inventoryEmpty')).toBeInTheDocument();
    expect(screen.getByText('qrScanResult.inventoryMore')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'qrScanResult.openSpools' }));
    expect(onOpenSpools).toHaveBeenCalledTimes(1);
    fireEvent.click(
      screen.getByRole('button', { name: 'qrScanResult.installInPrinter' }),
    );
    expect(onAddSpool).toHaveBeenCalledWith('printer');
  });

  it('shows historical counts when no usable spool remains', async () => {
    listSpools.mockResolvedValueOnce([
      makeSpool({ id: 31, state: 'archived' }),
      makeSpool({ id: 32, state: 'empty', remaining_weight_g: 0 }),
    ]);
    renderModal(baseResult);

    expect(await screen.findByText('qrScanResult.inventoryNoAvailable')).toBeInTheDocument();
    expect(screen.getByText('qrScanResult.inventoryArchived')).toBeInTheDocument();
    expect(screen.getByText('qrScanResult.inventoryEmpty')).toBeInTheDocument();
    expect(screen.queryByTestId('qr-inventory-spool-31')).not.toBeInTheDocument();
    expect(screen.queryByTestId('qr-inventory-spool-32')).not.toBeInTheDocument();
  });

  it('falls back to spool state when canonical location lookup fails', async () => {
    listPrinters.mockRejectedValueOnce(new Error('printers unavailable'));
    listSpools.mockResolvedValueOnce([makeSpool({ id: 41, state: 'active' })]);
    renderModal(baseResult);

    expect(await screen.findByText('qrScanResult.inventoryOne')).toBeInTheDocument();
    expect(screen.getByText('profilePage.spoolState.active')).toBeInTheDocument();
    expect(screen.getByText('QR Brand · Exact PLA')).toBeInTheDocument();
  });

  it('keeps recognition and explicit actions available when inventory fails', async () => {
    const onAddSpool = vi.fn();
    listSpools.mockRejectedValueOnce(new Error('inventory unavailable'));
    renderModal(baseResult, { onAddSpool });

    expect(await screen.findByText('qrScanResult.inventoryLoadError')).toBeInTheDocument();
    expect(screen.getByText('QR Brand · Exact PLA')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'qrScanResult.addToShelf' }));
    expect(onAddSpool).toHaveBeenCalledWith('shelf');
  });
});
