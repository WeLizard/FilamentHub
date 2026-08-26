import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { QrScanResponse } from '../api/client';
import { QrScanResultModal } from './QrScanResultModal';

const { savePreset } = vi.hoisted(() => ({ savePreset: vi.fn() }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../api/client', () => ({
  savedPresetsAPI: { save: savePreset },
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
  preset_saved: false,
  preset_sync_enabled: null,
} as QrScanResponse;

function renderModal(
  result: QrScanResponse,
  options: {
    isAuthenticated?: boolean;
    onRequestLogin?: () => void;
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
        isAuthenticated={options.isAuthenticated ?? true}
        onClose={vi.fn()}
        onRequestLogin={options.onRequestLogin}
      />
    </QueryClientProvider>,
  );
}

describe('QrScanResultModal', () => {
  beforeEach(() => {
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

  it('keeps anonymous recognition read-only and offers sign-in', () => {
    const onRequestLogin = vi.fn();
    renderModal(
      {
        ...baseResult,
        preset_saved: null,
        preset_sync_enabled: null,
      },
      { isAuthenticated: false, onRequestLogin },
    );

    expect(screen.getByText('qrScanResult.loginHint')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'qrScanResult.savePreset' }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'qrScanResult.login' }));
    expect(onRequestLogin).toHaveBeenCalledTimes(1);
    expect(savePreset).not.toHaveBeenCalled();
  });

  it('does not invent a preset when the catalog has none', () => {
    renderModal({
      ...baseResult,
      preset: null,
      preset_saved: null,
      preset_sync_enabled: null,
    });

    expect(screen.getByText('qrScanResult.noOfficialPreset')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'qrScanResult.savePreset' }),
    ).not.toBeInTheDocument();
  });
});
