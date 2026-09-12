import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode, type ReactNode } from 'react';
import { BrowserRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CatalogPage } from './CatalogPage';
import { navigateBackToCatalog } from '../utils/catalogReturnState';

const { listFilamentsMock } = vi.hoisted(() => ({ listFilamentsMock: vi.fn() }));
let nextFrameId = 1;
let frameQueue = new Map<number, FrameRequestCallback>();

async function flushAnimationFrame() {
  const callbacks = [...frameQueue.values()];
  frameQueue.clear();
  await act(async () => callbacks.forEach((callback) => callback(0)));
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: null }) }));
vi.mock('../hooks/useConfiguredNozzleHrc', () => ({ useConfiguredNozzleHrc: () => null }));
vi.mock('../hooks/useReaderCountry', () => ({ useReaderCountry: () => null }));
vi.mock('../components/SEOHead', () => ({ SEOHead: () => null }));
vi.mock('../api/client', () => ({
  filamentsAPI: {
    list: (...args: unknown[]) => listFilamentsMock(...args),
    getMaterialTypes: vi.fn().mockResolvedValue(['PLA']),
  },
  brandsAPI: { list: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 50, pages: 0 }), get: vi.fn() },
  printersAPI: { list: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 50, pages: 0 }) },
  physicalPrintersAPI: { list: vi.fn().mockResolvedValue([]) },
  savedPresetsAPI: { list: vi.fn().mockResolvedValue({ items: [] }), save: vi.fn() },
  qrAPI: { generate: vi.fn(), getQRCodeURL: vi.fn((id: number) => `/api/v1/qr/filament/${id}`) },
}));

const makeFilament = (id: number, name: string) => ({
  id, brand_id: 3, brand_name: 'FiberLab', brand_slug: 'fiberlab', brand_verified: true,
  slug: name.toLowerCase(), name, material_type: 'PLA', color_name: 'Blue', color_hex: '#0000ff',
  ral_code: null, visual_settings: null, additives: [], property_claims: [], diameter: 1.75,
  density: 1.24, price_per_kg: null, spool_weight: 1000, empty_spool_weight_g: 200,
  recommended_nozzle_temp_min: 200, recommended_nozzle_temp_max: 220,
  recommended_bed_temp_min: 50, recommended_bed_temp_max: 60, required_nozzle_hrc: null,
  description: null, views_count: 0, scans_count: 0, qr_code: null, active: true,
  availability: 'available', created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
  preset_summaries: [],
});

function DetailStub() {
  const navigate = useNavigate();
  const location = useLocation();
  return <button onClick={() => navigateBackToCatalog(navigate, location.state)}>Back</button>;
}

function CatalogRoute() {
  const navigate = useNavigate();
  const location = useLocation();
  return <>
    <button onClick={() => navigate(-1)}>History back</button>
    <output data-testid="location">{`${location.pathname}${location.search}${location.hash}`}</output>
    <CatalogPage />
  </>;
}

function mountFlow(strict = false) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  const router = <BrowserRouter>
    <Routes>
      <Route path="/" element={<CatalogRoute />} />
      <Route path="/previous" element={<p>Previous page</p>} />
      <Route path="/brands/:brand/filaments/:filament" element={<DetailStub />} />
    </Routes>
  </BrowserRouter>;
  const content: ReactNode = strict ? <StrictMode>{router}</StrictMode> : router;
  const view = render(
    <QueryClientProvider client={queryClient}>
      {content}
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
}

function renderFlow(url = '/?q=PLA&auth=login#results', withPrevious = false, strict = false) {
  if (withPrevious) {
    window.history.replaceState({}, document.title, '/previous');
    window.history.pushState({}, document.title, url);
  } else {
    window.history.replaceState({}, document.title, url);
  }
  return mountFlow(strict);
}

describe('catalog detail return navigation', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, document.title);
    Object.defineProperty(window.history, 'scrollRestoration', {
      configurable: true,
      writable: true,
      value: 'auto',
    });
    nextFrameId = 1;
    frameQueue = new Map();
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(),
    }));
    vi.stubGlobal('IntersectionObserver', class {
      observe() {} disconnect() {} unobserve() {} takeRecords() { return []; }
    });
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      const id = nextFrameId++;
      frameQueue.set(id, callback);
      return id;
    });
    vi.stubGlobal('cancelAnimationFrame', (id: number) => { frameQueue.delete(id); });
    vi.stubGlobal('scrollTo', vi.fn());
    vi.stubGlobal('scrollY', 500);
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      const top = this.id === 'catalog-filament-18' ? 240 : 0;
      return { top, left: 0, right: 0, bottom: top, width: 0, height: 0, x: 0, y: top, toJSON: () => ({}) };
    });
    listFilamentsMock.mockImplementation(async (params: { page?: number }) => ({
      items: params.page === 2 ? [makeFilament(18, 'Second')] : [makeFilament(17, 'First')],
      total: 2, page: params.page ?? 1, size: 24, pages: 2, printer_matched_ids: [],
    }));
  });

  it('returns through browser history and restores an item from a cached second page', async () => {
    const firstMount = renderFlow('/?q=PLA&auth=login#results', false, true);
    fireEvent.click(await screen.findByRole('button', { name: 'catalogPage.loadMore' }));
    const second = await screen.findByRole('link', { name: 'Second' });
    fireEvent.click(second);
    fireEvent.click(await screen.findByRole('button', { name: 'Back' }));

    expect(await screen.findByRole('link', { name: 'Second' })).toBeInTheDocument();
    await waitFor(() => expect(firstMount.queryClient.isFetching({ queryKey: ['filaments'] })).toBe(0));
    expect(window.history.state.filamentHubCatalogReturn).toBeDefined();
    expect(frameQueue.size).toBeGreaterThan(0);
    expect(window.history.scrollRestoration).toBe('manual');
    await flushAnimationFrame();
    await flushAnimationFrame();
    await waitFor(() => expect(window.scrollTo).toHaveBeenCalledWith({ top: 500, behavior: 'auto' }));
    expect(window.history.state.filamentHubCatalogReturn).toBeUndefined();
    expect(window.history.scrollRestoration).toBe('auto');

    firstMount.unmount();
    mountFlow();
    await screen.findByRole('link', { name: 'First' });
    await flushAnimationFrame();
    await flushAnimationFrame();
    expect(window.scrollTo).toHaveBeenCalledTimes(1);
  });

  it('falls back to the top when the recorded item is absent from rendered cache', async () => {
    const { queryClient } = renderFlow();
    fireEvent.click(await screen.findByRole('button', { name: 'catalogPage.loadMore' }));
    fireEvent.click(await screen.findByRole('link', { name: 'Second' }));
    queryClient.removeQueries({ queryKey: ['filaments'] });
    fireEvent.click(await screen.findByRole('button', { name: 'Back' }));
    await screen.findByRole('link', { name: 'First' });
    await waitFor(() => expect(queryClient.isFetching({ queryKey: ['filaments'] })).toBe(0));
    await flushAnimationFrame();
    await flushAnimationFrame();
    await waitFor(() => expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'auto' }));
  });

  it('replaces transient filter changes while preserving auth, unrelated params and hash', async () => {
    renderFlow('/?auth=login&future=1#results', true);
    fireEvent.change(await screen.findByPlaceholderText('catalogPage.searchPlaceholder'), {
      target: { value: 'ABS' },
    });
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(
      '/?auth=login&future=1&q=ABS#results',
    ));
    fireEvent.click(screen.getByRole('button', { name: 'History back' }));
    expect(await screen.findByText('Previous page')).toBeInTheDocument();
  });
});
