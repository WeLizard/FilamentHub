import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { PropsWithChildren } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useConfigurationPresetRecommendation } from './useConfigurationPresetRecommendation';

const {
  getRecommended,
  listPrinters,
  listProfiles,
  persistSelection,
} = vi.hoisted(() => ({
  getRecommended: vi.fn(),
  listPrinters: vi.fn(),
  listProfiles: vi.fn(),
  persistSelection: vi.fn(),
}));

vi.mock('../api/client', () => ({
  physicalPrintersAPI: { list: listPrinters },
  printerProfilesAPI: { listAllOwned: listProfiles },
  presetsAPI: { getRecommendedForConfiguration: getRecommended },
}));

vi.mock('./usePrinterSelection', () => ({
  usePrinterSelection: () => [
    { physicalPrinterId: null, printerProfileId: null },
    persistSelection,
  ],
}));

describe('useConfigurationPresetRecommendation', () => {
  beforeEach(() => {
    listPrinters.mockReset();
    listProfiles.mockReset();
    getRecommended.mockReset();
    persistSelection.mockReset();
    listPrinters.mockResolvedValue([{
      id: 31,
      name: 'My Voron',
      printer_profile_ids: [91],
    }]);
    listProfiles.mockResolvedValue([{
      id: 91,
      printer_id: 7,
      name: 'Voron 0.4',
      active: true,
    }]);
    getRecommended.mockResolvedValue({
      printer_id: 7,
      printer_name: 'Voron 2.4',
      items: [{ preset: { id: 88, name: 'Compatible preset' } }],
    });
  });

  it('uses the existing read-only recommendation endpoint for the selected configuration', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(
      () => useConfigurationPresetRecommendation(15, 42),
      { wrapper },
    );

    await waitFor(() => expect(result.current.options).toHaveLength(1));
    act(() => result.current.select('31:91'));

    expect(persistSelection).toHaveBeenCalledWith({
      physicalPrinterId: 31,
      printerProfileId: 91,
    });
    await waitFor(() => {
      expect(getRecommended).toHaveBeenCalledWith({
        physical_printer_id: 31,
        printer_profile_id: 91,
        filament_id: 42,
        limit: 20,
      });
      expect(result.current.recommendation?.preset.id).toBe(88);
    });
  });

  it('does not request recommendations until a configuration is selected', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(
      () => useConfigurationPresetRecommendation(15, 42),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isLoadingOptions).toBe(false));
    expect(getRecommended).not.toHaveBeenCalled();
  });
});
