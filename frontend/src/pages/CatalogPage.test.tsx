import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CatalogPage } from './CatalogPage';

const { listFilamentsMock, listBrandsMock, listPrintersMock } = vi.hoisted(() => ({
  listFilamentsMock: vi.fn(),
  listBrandsMock: vi.fn(),
  listPrintersMock: vi.fn(),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useLocation: () => ({ pathname: '/', search: '', hash: '', state: null, key: 'test' }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: null }),
}));

vi.mock('../hooks/useConfiguredNozzleHrc', () => ({
  useConfiguredNozzleHrc: () => null,
}));

vi.mock('../components/SEOHead', () => ({
  SEOHead: () => null,
}));

vi.mock('../api/client', () => ({
  filamentsAPI: {
    list: (...args: unknown[]) => listFilamentsMock(...args),
    getMaterialTypes: vi.fn().mockResolvedValue(['PLA', 'PETG']),
  },
  brandsAPI: {
    list: (...args: unknown[]) => listBrandsMock(...args),
    get: vi.fn(),
  },
  printersAPI: {
    list: (...args: unknown[]) => listPrintersMock(...args),
  },
  physicalPrintersAPI: {
    list: vi.fn().mockResolvedValue([]),
  },
  savedPresetsAPI: {
    list: vi.fn().mockResolvedValue({ items: [] }),
    save: vi.fn(),
  },
  qrAPI: {
    generate: vi.fn(),
  },
}));

describe('CatalogPage', () => {
  let intersectionCallback: ((entries: Array<{ isIntersecting: boolean }>) => void) | null;

  beforeEach(() => {
    intersectionCallback = null;
    class FakeIntersectionObserver {
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
      takeRecords = vi.fn(() => []);

      constructor(callback: (entries: Array<{ isIntersecting: boolean }>) => void) {
        intersectionCallback = callback;
      }
    }
    vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);
    listFilamentsMock.mockReset();
    listFilamentsMock.mockImplementation(async (params: { page?: number }) => ({
      items: [],
      total: 101,
      page: params.page ?? 1,
      size: 24,
      pages: 5,
      printer_matched_ids: [],
    }));
    listBrandsMock.mockReset();
    listBrandsMock.mockResolvedValue({ items: [], total: 0, page: 1, size: 50, pages: 0 });
    listPrintersMock.mockReset();
    listPrintersMock.mockResolvedValue({ items: [], total: 0, page: 1, size: 50, pages: 0 });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads additional catalog batches and sends search terms to the server', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <CatalogPage />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(listFilamentsMock).toHaveBeenCalledWith(
        expect.objectContaining({ page: 1, size: 24, search: undefined }),
      );
    });

    fireEvent.click(await screen.findByRole('button', { name: 'catalogPage.loadMore' }));
    await waitFor(() => {
      expect(listFilamentsMock).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2, size: 24 }),
      );
    });

    fireEvent.change(screen.getByPlaceholderText('catalogPage.searchPlaceholder'), {
      target: { value: 'Sakura' },
    });
    await waitFor(() => {
      expect(listFilamentsMock).toHaveBeenCalledWith(
        expect.objectContaining({ page: 1, search: 'Sakura' }),
      );
    });
  });

  it('automatically loads the next batch when the catalog footer approaches the viewport', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <CatalogPage />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(intersectionCallback).not.toBeNull();
      expect(listFilamentsMock).toHaveBeenCalledWith(
        expect.objectContaining({ page: 1, size: 24 }),
      );
    });

    act(() => {
      intersectionCallback?.([{ isIntersecting: true }]);
    });

    await waitFor(() => {
      expect(listFilamentsMock).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2, size: 24 }),
      );
    });
  });
});
