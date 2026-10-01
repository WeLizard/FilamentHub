import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const state = vi.hoisted(() => ({
  user: null as { role: string; legal_onboarding_required: boolean } | null,
  isMaintenanceMode: false,
  maintenanceMessage: '',
  clearMaintenanceMode: () => undefined,
}));
const api = vi.hoisted(() => ({ report: vi.fn() }));

vi.mock('../contexts/AuthContext', () => ({
  AuthProvider: ({ children }: { children: unknown }) => children,
  useAuth: () => state,
}));
vi.mock('../api/client', () => ({ orcaSlicesAPI: api }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../components/Layout', () => ({ Layout: ({ children }: { children: unknown }) => children }));
vi.mock('../pages/CatalogPage', () => ({ CatalogPage: () => null }));
vi.mock('../components/Toast', () => ({ ToastContainer: () => null, toast: { show: vi.fn() } }));
vi.mock('../hooks/useCurrencyCatalogue', () => ({ useCurrencyCatalogue: () => undefined }));
vi.mock('../hooks/useTokenRefresh', () => ({ useTokenRefresh: () => undefined }));
vi.mock('../hooks/usePluginDeveloperMode', () => ({ usePluginDeveloperMode: () => false }));

import App from '../App';

const SLICE_REQUEST_ID = `slice-report-${'b'.repeat(32)}`;
const signedInUser = { role: 'user', legal_onboarding_required: false };

function renderApp() {
  const client = new QueryClient();
  const tree = () => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/embed/catalog']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
  const view = render(tree());
  return { rerender: () => view.rerender(tree()), unmount: view.unmount };
}

function postedTypes(postMessage: ReturnType<typeof vi.fn>, type: string) {
  return postMessage.mock.calls.filter(([message]) => message.type === type);
}

function setVisibility(value: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { configurable: true, value });
}

describe('embedded slice report delivery', () => {
  const originalParent = window.parent;
  let postMessage: ReturnType<typeof vi.fn>;
  let parent: { postMessage: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-01T10:00:00Z'));
    postMessage = vi.fn();
    parent = { postMessage };
    Object.defineProperty(window, 'parent', { configurable: true, value: parent });
    window.history.pushState({}, '', '/embed/catalog');
    setVisibility('visible');
    state.user = signedInUser;
    api.report.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    Object.defineProperty(window, 'parent', { configurable: true, value: originalParent });
    window.history.pushState({}, '', '/');
  });

  it('asks once on load and never again on a timer', async () => {
    const app = renderApp();
    expect(postedTypes(postMessage, 'request-slice-reports')).toHaveLength(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(10 * 60_000); });

    expect(postedTypes(postMessage, 'request-slice-reports')).toHaveLength(1);
    expect(vi.getTimerCount()).toBe(0);
    app.unmount();
  });

  it('asks once when the user signs in and not for a guest', () => {
    state.user = null;
    const app = renderApp();
    expect(postedTypes(postMessage, 'request-slice-reports')).toHaveLength(0);

    state.user = signedInUser;
    app.rerender();
    expect(postedTypes(postMessage, 'request-slice-reports')).toHaveLength(1);

    app.rerender();
    expect(postedTypes(postMessage, 'request-slice-reports')).toHaveLength(1);
    app.unmount();
  });

  it('asks once when the window comes back, however many events announce it', async () => {
    const app = renderApp();
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });

    setVisibility('hidden');
    document.dispatchEvent(new Event('visibilitychange'));
    expect(postedTypes(postMessage, 'request-slice-reports')).toHaveLength(1);

    setVisibility('visible');
    document.dispatchEvent(new Event('visibilitychange'));
    window.dispatchEvent(new Event('focus'));
    expect(postedTypes(postMessage, 'request-slice-reports')).toHaveLength(2);

    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    window.dispatchEvent(new Event('focus'));
    expect(postedTypes(postMessage, 'request-slice-reports')).toHaveLength(3);

    app.unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    window.dispatchEvent(new Event('focus'));
    expect(postedTypes(postMessage, 'request-slice-reports')).toHaveLength(3);
  });

  it('delivers a batch the plugin pushes and acknowledges it without asking again', async () => {
    api.report.mockResolvedValue({ accepted: 1, duplicates: 0 });
    const app = renderApp();
    const requestsBefore = postedTypes(postMessage, 'request-slice-reports').length;

    await act(async () => {
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: 'filamenthub-plugin',
          type: 'slice-report-batch',
          requestId: SLICE_REQUEST_ID,
          slices: [{ file_name: 'cube.gcode', source_key: 'key-1' }],
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
    });

    expect(api.report).toHaveBeenCalledTimes(1);
    const [result] = postedTypes(postMessage, 'slice-report-result');
    expect(result[0]).toMatchObject({ requestId: SLICE_REQUEST_ID, sourceKeys: ['key-1'], ok: true });
    expect(postedTypes(postMessage, 'request-slice-reports')).toHaveLength(requestsBefore);
    app.unmount();
  });

  it('reports a failed delivery and leaves the retry to the next focus or push', async () => {
    api.report.mockRejectedValue(new Error('offline'));
    const app = renderApp();

    await act(async () => {
      window.dispatchEvent(new MessageEvent('message', {
        data: {
          source: 'filamenthub-plugin',
          type: 'slice-report-batch',
          requestId: SLICE_REQUEST_ID,
          slices: [{ file_name: 'cube.gcode', source_key: 'key-1' }],
        },
        origin: window.location.origin,
        source: parent as unknown as Window,
      }));
    });
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });

    const [result] = postedTypes(postMessage, 'slice-report-result');
    expect(result[0]).toMatchObject({ ok: false });
    expect(api.report).toHaveBeenCalledTimes(1);
    expect(postedTypes(postMessage, 'request-slice-reports')).toHaveLength(1);

    window.dispatchEvent(new Event('focus'));
    expect(postedTypes(postMessage, 'request-slice-reports')).toHaveLength(2);
    app.unmount();
  });
});
