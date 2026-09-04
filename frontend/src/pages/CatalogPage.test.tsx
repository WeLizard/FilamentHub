import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CatalogPage } from './CatalogPage';

const { listFilamentsMock, listBrandsMock, listPrintersMock, navigateMock } = vi.hoisted(() => ({
  listFilamentsMock: vi.fn(),
  listBrandsMock: vi.fn(),
  listPrintersMock: vi.fn(),
  navigateMock: vi.fn(),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => navigateMock,
  useLocation: () => ({ pathname: '/', search: '', hash: '', state: null, key: 'test' }),
  Link: ({ to, children, ...props }: { to: string; children: React.ReactNode }) => (
    <a href={to} {...props}>{children}</a>
  ),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
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
    getQRCodeURL: vi.fn((id: number) => `/api/v1/qr/filament/${id}`),
  },
}));

const catalogFilament = {
  id: 17,
  brand_id: 3,
  brand_name: 'FiberLab',
  brand_slug: 'fiberlab',
  brand_verified: true,
  name: 'PETG CF',
  material_type: 'PETG',
  color_name: 'Graphite',
  color_hex: '#303238',
  ral_code: null,
  visual_settings: { filler: 'carbon', effects: ['carbon'] },
  additives: [{ code: 'carbon_fiber', content_percent: 15, content_basis: 'weight' }],
  property_claims: [{ code: 'wear_resistant' }],
  diameter: 1.75,
  density: 1.24,
  price_per_kg: null,
  spool_weight: 750,
  empty_spool_weight_g: 210,
  recommended_nozzle_temp_min: 235,
  recommended_nozzle_temp_max: 255,
  recommended_bed_temp_min: 70,
  recommended_bed_temp_max: 85,
  required_nozzle_hrc: 50,
  description: null,
  views_count: 0,
  scans_count: 0,
  qr_code: null,
  active: true,
  availability: 'available',
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
  preset_summaries: [],
} as const;

const catalogResponse = (items: unknown[]) => ({
  items,
  total: items.length,
  page: 1,
  size: 24,
  pages: 1,
  printer_matched_ids: [],
});

const interactiveTableFilament = {
  ...catalogFilament,
  slug: 'petg-cf',
  ral_code: '7024',
  qr_code: 'FHUB-17',
  preset_summaries: [{
    id: 101,
    name: 'Balanced PETG CF',
    is_official: true,
    is_weighted: false,
    extruder_temp: 245,
    bed_temp: 80,
    fan_speed: 40,
    flow_rate: 98,
    rating: 4.8,
    success_rate: 96,
    updated_at: '2026-08-01T00:00:00Z',
    preset_type: 'official',
  }],
} as const;

function stubDesktopLayout(matches: boolean) {
  vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })));
}

describe('CatalogPage', () => {
  let intersectionCallback: ((entries: Array<{ isIntersecting: boolean }>) => void) | null;

  beforeEach(() => {
    window.localStorage.clear();
    stubDesktopLayout(false);
    navigateMock.mockReset();
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

    fireEvent.focus(screen.getByPlaceholderText('catalogPage.allColors'));
    fireEvent.click(await screen.findByRole('button', { name: 'colorGroups.red' }));
    await waitFor(() => {
      expect(listFilamentsMock).toHaveBeenCalledWith(
        expect.objectContaining({ page: 1, color_group: 'red' }),
      );
    });

    fireEvent.focus(screen.getByPlaceholderText('catalogPage.allColors'));
    fireEvent.click(await screen.findByRole('button', { name: 'catalogPage.multicolor' }));
    await waitFor(() => {
      expect(listFilamentsMock).toHaveBeenCalledWith(
        expect.objectContaining({ page: 1, color_group: undefined, multicolor: true }),
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

  it('shows catalog-level buying facts without promoting standard diameter or density', async () => {
    listFilamentsMock.mockResolvedValue(catalogResponse([catalogFilament]));

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <CatalogPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('PETG CF')).toBeInTheDocument();
    expect(screen.getByText('235\u2013255°C')).toBeInTheDocument();
    expect(screen.getByText('70\u201385°C')).toBeInTheDocument();
    expect(screen.getByText('filamentFeatures.additives.carbon_fiber 15%')).toBeInTheDocument();
    expect(screen.getByText('filamentFeatures.claims.wear_resistant')).toBeInTheDocument();
    expect(screen.queryByText('1.75 catalogPage.units.mm')).not.toBeInTheDocument();
    expect(screen.queryByText('1.24 catalogPage.units.gcm3')).not.toBeInTheDocument();
  });

  it('switches to the table without refetching and restores the remembered view', async () => {
    stubDesktopLayout(true);
    listFilamentsMock.mockResolvedValue(catalogResponse([interactiveTableFilament]));

    const renderCatalog = () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      return render(
        <QueryClientProvider client={queryClient}>
          <CatalogPage />
        </QueryClientProvider>,
      );
    };

    const firstRender = renderCatalog();
    expect(await screen.findByText('PETG CF')).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'catalogPage.tableCaption' })).not.toBeInTheDocument();
    const searchPanel = screen.getByPlaceholderText('catalogPage.searchPlaceholder').closest('.glass-panel');
    expect(searchPanel).toContainElement(screen.getByRole('group', { name: 'catalogPage.viewMode' }));
    expect(searchPanel).toHaveTextContent('catalogPage.resultsRange');
    const callsBeforeSwitch = listFilamentsMock.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: 'catalogPage.tableView' }));

    const table = await screen.findByRole('table', { name: 'catalogPage.tableCaption' });
    expect(table).toBeInTheDocument();
    expect(table.parentElement).toHaveClass('overflow-hidden');
    expect(table.className).not.toContain('min-w-');
    expect(listFilamentsMock).toHaveBeenCalledTimes(callsBeforeSwitch);
    expect(JSON.parse(window.localStorage.getItem('filamenthub.ui-state') ?? '{}')).toMatchObject({
      anonymous: { 'catalog.resultsView': 'list' },
    });

    const row = screen.getByText('PETG CF').closest('tr');
    expect(row).not.toBeNull();
    expect(row?.children[0]).toHaveTextContent('Graphite');
    expect(row?.children[0]).toHaveTextContent('RAL 7024');
    expect(row?.children[2]).not.toHaveTextContent('Graphite');
    expect(screen.queryByRole('link', { name: 'catalogPage.openMaterial' })).not.toBeInTheDocument();

    const addButton = screen.getByRole('button', { name: 'catalogPage.addToProfile' });
    const qrButton = screen.getByRole('button', { name: 'catalogPage.qrCode' });
    for (const button of [addButton, qrButton]) {
      expect(button).toHaveClass('size-10', 'shrink-0');
      expect(button.querySelector('svg')).not.toBeNull();
    }

    fireEvent.click(qrButton);
    expect(navigateMock).not.toHaveBeenCalled();
    expect(await screen.findByRole('img', { name: 'QR PETG CF' })).toBeInTheDocument();

    fireEvent.click(row!);
    expect(navigateMock).toHaveBeenCalledWith('/brands/fiberlab/filaments/petg-cf');

    firstRender.unmount();
    renderCatalog();

    expect(await screen.findByRole('table', { name: 'catalogPage.tableCaption' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'catalogPage.tableView' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('keeps the saved table preference while rendering cards on a narrow screen', async () => {
    window.localStorage.setItem('filamenthub.ui-state', JSON.stringify({
      anonymous: { 'catalog.resultsView': 'list' },
    }));
    listFilamentsMock.mockResolvedValue(catalogResponse([catalogFilament]));

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <CatalogPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('PETG CF')).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'catalogPage.tableCaption' })).not.toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem('filamenthub.ui-state') ?? '{}')).toMatchObject({
      anonymous: { 'catalog.resultsView': 'list' },
    });
  });
});
