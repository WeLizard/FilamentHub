import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AxiosError, CanceledError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';
import { QueryClient, QueryObserver } from '@tanstack/react-query';

const state = vi.hoisted(() => ({
  api: null as AxiosInstance | null,
  adapter: vi.fn(), post: vi.fn(), reportPlugin: vi.fn(),
  access: 'access-a' as string | null, refresh: 'refresh-a' as string | null,
  cookie: false, csrf: null as string | null, plugin: false,
  remove: vi.fn(),
}));

vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>();
  return { ...actual, default: {
    ...actual.default,
    create: (config: Parameters<typeof actual.default.create>[0]) => {
      const api = actual.default.create(config);
      api.defaults.adapter = (request) => state.adapter(request);
      state.api = api;
      return api;
    },
    post: state.post,
  } };
});
vi.mock('../utils/auth', () => ({
  getToken: () => state.access, getRefreshToken: () => state.refresh,
  getCsrfToken: () => state.csrf, isCookieAuthMode: () => state.cookie,
  isJwtAuthMode: () => !state.cookie, isOrcaEmbedded: () => false,
  shouldPersistTokensLocally: () => !state.cookie,
  setToken: (token: string) => { state.access = token; },
  setRefreshToken: (token: string) => { state.refresh = token; },
  removeToken: () => { state.remove(); state.access = null; state.refresh = null; },
}));
vi.mock('../utils/pluginBridge', () => ({
  isPluginEmbed: () => state.plugin, reportPluginSessionToPlugin: state.reportPlugin,
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
function failure(config: InternalAxiosRequestConfig, status = 401, code = 'ERR_INVALID_TOKEN') {
  return new AxiosError('Request rejected', 'ERR_BAD_REQUEST', config, undefined, {
    config, status, statusText: 'Rejected', headers: {}, data: { detail: { code } },
  });
}
const refreshed = { data: { access_token: 'access-new', refresh_token: 'refresh-new' } };
const until = async (condition: () => boolean) => { await vi.waitFor(() => expect(condition()).toBe(true)); };
async function load() { vi.resetModules(); return import('../api/client'); }

describe('account request lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.adapter.mockReset(); state.post.mockReset();
    state.access = 'access-a'; state.refresh = 'refresh-a';
    state.cookie = false; state.csrf = null; state.plugin = false;
  });

  it.each([
    ['spools', 'logout'], ['spools', 'unmount'],
    ['printers', 'logout'], ['printers', 'unmount'],
  ])('aborts the %s HTTP transport on %s', async (resource, boundary) => {
    const { spoolsAPI, physicalPrintersAPI } = await load();
    const aborted = vi.fn();
    state.adapter.mockImplementation((config) => new Promise((_, reject) => {
      config.signal?.addEventListener('abort', () => {
        aborted();
        reject(new CanceledError(undefined, config));
      }, { once: true });
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const observer = new QueryObserver<unknown>(client, {
      queryKey: [resource],
      queryFn: ({ signal }) => resource === 'spools'
        ? spoolsAPI.list(signal) : physicalPrintersAPI.list(signal),
    });
    const unsubscribe = observer.subscribe(() => {});
    try {
      await until(() => state.adapter.mock.calls.length === 1);
      const request = state.adapter.mock.calls[0][0];
      expect(request.signal).toBeInstanceOf(AbortSignal);
      if (boundary === 'logout') await client.cancelQueries();
      else unsubscribe();
      expect(request.signal.aborted).toBe(true);
      expect(aborted).toHaveBeenCalledOnce();
      expect(state.post).not.toHaveBeenCalled();
      expect(state.remove).not.toHaveBeenCalled();
    } finally {
      unsubscribe();
      client.clear();
    }
  });

  it('returns wrong-password business rejection without refresh or repeated mutation', async () => {
    await load();
    state.adapter.mockImplementation(async (config) => { throw failure(config, 401, 'ERR_WRONG_PASSWORD'); });
    await expect(state.api!.patch('/auth/me/password', { current_password: 'wrong' })).rejects.toMatchObject({ response: { status: 401 } });
    expect(state.adapter).toHaveBeenCalledOnce();
    expect(state.post).not.toHaveBeenCalled();
    expect(state.remove).not.toHaveBeenCalled();
  });

  it('propagates a definitive scheduled refresh rejection as an expiry event', async () => {
    const { authAPI } = await load();
    const expired = vi.fn();
    window.addEventListener('authSessionExpired', expired);
    try {
      state.post.mockRejectedValue({ response: { status: 401 } });
      await expect(authAPI.refresh()).rejects.toMatchObject({ response: { status: 401 } });
      expect(expired).toHaveBeenCalledOnce();
      expect(state.remove).toHaveBeenCalledOnce();
    } finally { window.removeEventListener('authSessionExpired', expired); }
  });

  it.each([403, 500])('does not expire a scheduled refresh on status %s', async (status) => {
    const { authAPI } = await load();
    const expired = vi.fn();
    window.addEventListener('authSessionExpired', expired);
    try {
      state.post.mockRejectedValue({ response: { status } });
      await expect(authAPI.refresh()).rejects.toMatchObject({ response: { status } });
      expect(expired).not.toHaveBeenCalled();
      expect(state.remove).not.toHaveBeenCalled();
    } finally { window.removeEventListener('authSessionExpired', expired); }
  });

  it('does not expire a replacement account on an old scheduled refresh rejection', async () => {
    const { authAPI, beginAuthSessionTransition } = await load();
    const expired = vi.fn();
    window.addEventListener('authSessionExpired', expired);
    try {
      const response = deferred<never>();
      state.post.mockReturnValue(response.promise);
      const request = authAPI.refresh().catch((error) => error);
      await until(() => state.post.mock.calls.length === 1);
      beginAuthSessionTransition();
      state.access = 'access-b'; state.refresh = 'refresh-b';
      response.reject({ response: { status: 401 } });
      await request;
      expect(expired).not.toHaveBeenCalled();
      expect(state.access).toBe('access-b');
    } finally { window.removeEventListener('authSessionExpired', expired); }
  });

  it('gives a replacement account its own refresh instead of inheriting an older rejection', async () => {
    const { beginAuthSessionTransition } = await load();
    const oldRefresh = deferred<never>();
    state.post.mockReturnValueOnce(oldRefresh.promise).mockResolvedValueOnce({
      data: { access_token: 'access-b-new', refresh_token: 'refresh-b-new' },
    });
    state.adapter.mockImplementation(async (config) => {
      if (config.url === '/private-b' && config._retry) {
        return { data: { owner: 'b' }, status: 200, headers: {}, config };
      }
      throw failure(config);
    });
    const oldRequest = state.api!.get('/auth/me').catch((error) => error);
    await until(() => state.post.mock.calls.length === 1);
    beginAuthSessionTransition();
    state.access = 'access-b'; state.refresh = 'refresh-b';
    const newRequest = state.api!.get('/private-b').catch((error) => error);
    await until(() => state.adapter.mock.calls.length === 2);
    oldRefresh.reject({ response: { status: 401 } });
    await oldRequest;
    expect(await newRequest).toMatchObject({ data: { owner: 'b' } });
    expect(state.post).toHaveBeenCalledTimes(2);
    expect(state.access).toBe('access-b-new');
    expect(state.remove).not.toHaveBeenCalled();
  });

  it('bounds every concurrent unauthorized request to one retry', async () => {
    await load();
    const refresh = deferred<typeof refreshed>();
    state.post.mockReturnValue(refresh.promise);
    state.adapter.mockImplementation(async (config) => { throw failure(config); });
    const requests = Promise.allSettled([state.api!.get('/auth/me'), state.api!.get('/private-b')]);
    await until(() => state.adapter.mock.calls.length === 2 && state.post.mock.calls.length === 1);
    refresh.resolve(refreshed);
    const results = await requests;
    expect(results.every((result) => result.status === 'rejected')).toBe(true);
    expect(state.post).toHaveBeenCalledOnce();
    expect(state.adapter.mock.calls.map(([config]) => config.url).sort()).toEqual(['/auth/me', '/auth/me', '/private-b', '/private-b']);
  });

  it('never replays an old-account mutation when its 401 arrives after a new login', async () => {
    const { beginAuthSessionTransition } = await load();
    const oldResponse = deferred<never>();
    state.adapter.mockReturnValue(oldResponse.promise);
    const result = state.api!.patch('/private-mutation', { value: 'a' }).catch((error) => error);
    await until(() => state.adapter.mock.calls.length === 1);
    const oldConfig = state.adapter.mock.calls[0][0];
    beginAuthSessionTransition();
    state.access = 'access-b'; state.refresh = 'refresh-b';
    oldResponse.reject(failure(oldConfig));
    expect(await result).toMatchObject({ name: 'StaleRefreshResponseError' });
    expect(state.adapter).toHaveBeenCalledOnce();
    expect(state.post).not.toHaveBeenCalled();
    expect(state.access).toBe('access-b');
    expect(state.remove).not.toHaveBeenCalled();
  });

  it('does not clear a new account on a stale refresh failure', async () => {
    const { beginAuthSessionTransition } = await load();
    const refresh = deferred<never>();
    state.post.mockReturnValue(refresh.promise);
    state.adapter.mockImplementation(async (config) => { throw failure(config); });
    const result = state.api!.get('/auth/me').catch((error) => error);
    await until(() => state.post.mock.calls.length === 1);
    beginAuthSessionTransition();
    state.access = 'access-b'; state.refresh = 'refresh-b';
    refresh.reject({ response: { status: 401 } });
    expect(await result).toMatchObject({ name: 'StaleRefreshResponseError' });
    expect(state.access).toBe('access-b');
    expect(state.remove).not.toHaveBeenCalled();
  });

  it('rejects a late success before an old mutation can run cache-updating callbacks', async () => {
    const { beginAuthSessionTransition } = await load();
    const response = deferred<any>();
    state.adapter.mockReturnValue(response.promise);
    const onSuccess = vi.fn();
    const request = state.api!.patch('/private-mutation', {}).then(onSuccess).catch((error) => error);
    await until(() => state.adapter.mock.calls.length === 1);
    beginAuthSessionTransition();
    response.resolve({ data: { owner: 'account-a' }, config: state.adapter.mock.calls[0][0], status: 200, headers: {} });
    expect(await request).toMatchObject({ name: 'StaleRefreshResponseError' });
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('cancels a queued request without replay or timeout misclassification', async () => {
    await load();
    const refresh = deferred<typeof refreshed>();
    state.post.mockReturnValue(refresh.promise);
    state.adapter.mockImplementation(async (config) => {
      if (!config._retry) throw failure(config);
      return { data: {}, status: 200, headers: {}, config };
    });
    const first = state.api!.get('/auth/me');
    await until(() => state.post.mock.calls.length === 1);
    const controller = new AbortController();
    const second = state.api!.get('/private-b', { signal: controller.signal }).catch((error) => error);
    await until(() => state.adapter.mock.calls.length === 2);
    controller.abort();
    const canceled = await second;
    expect(canceled.code).toBe('ERR_CANCELED');
    expect(canceled.response).toBeUndefined();
    refresh.resolve(refreshed);
    await first;
    expect(state.adapter.mock.calls.filter(([config]) => config.url === '/private-b')).toHaveLength(1);
    state.adapter.mockRejectedValue(new CanceledError());
    await expect(state.api!.get('/public')).rejects.toMatchObject({ code: 'ERR_CANCELED' });
  });

  it.each([500, 503, 0])('preserves credentials when refresh fails with transport status %s', async (status) => {
    await load();
    state.adapter.mockImplementation(async (config) => { throw failure(config); });
    const error = status ? { response: { status } } : new Error('offline');
    state.post.mockRejectedValue(error);
    await expect(state.api!.get('/auth/me')).rejects.toBe(error);
    expect(state.access).toBe('access-a');
    expect(state.remove).not.toHaveBeenCalled();
  });

  it('does not notify the plugin or replay after a delayed capability crosses logout', async () => {
    const { beginAuthSessionTransition } = await load();
    state.plugin = true;
    const capability = deferred<{ data: { plugin_token: string } }>();
    state.post.mockResolvedValueOnce(refreshed).mockReturnValueOnce(capability.promise);
    state.adapter.mockImplementation(async (config) => { throw failure(config); });
    const result = state.api!.get('/auth/me').catch((error) => error);
    await until(() => state.post.mock.calls.length === 2);
    beginAuthSessionTransition();
    capability.resolve({ data: { plugin_token: 'obsolete' } });
    expect(await result).toMatchObject({ name: 'StaleRefreshResponseError' });
    expect(state.reportPlugin).not.toHaveBeenCalled();
    expect(state.adapter).toHaveBeenCalledOnce();
  });

  it('serializes external token restoration and login behind pending logout', async () => {
    const { authAPI, withAuthSessionLock } = await load();
    const response = deferred<{ data: null }>();
    state.post.mockReturnValue(response.promise);
    state.adapter.mockImplementation(async (config) => ({ data: refreshed.data, config, status: 200, headers: {} }));
    const logout = authAPI.logout();
    const restore = withAuthSessionLock(async () => { state.access = 'restored'; state.refresh = 'restored-refresh'; });
    const login = authAPI.login({ email: 'next@example.com', password: 'password' });
    await until(() => state.post.mock.calls.length === 1);
    expect(state.access).toBe('access-a');
    expect(state.adapter).not.toHaveBeenCalled();
    response.resolve({ data: null });
    await Promise.all([logout, restore, login]);
    expect(state.access).toBe('restored');
    expect(state.remove).toHaveBeenCalledOnce();
    expect(state.adapter).toHaveBeenCalledOnce();
  });

  it('does not refresh an anonymous cookie probe but accepts a readable CSRF candidate', async () => {
    state.cookie = true; state.access = null; state.refresh = null;
    await load();
    state.adapter.mockImplementation(async (config) => { throw failure(config); });
    await expect(state.api!.get('/auth/me')).rejects.toMatchObject({ response: { status: 401 } });
    expect(state.post).not.toHaveBeenCalled();
    state.csrf = 'candidate';
    state.post.mockResolvedValue(refreshed);
    await expect(state.api!.get('/auth/me')).rejects.toMatchObject({ response: { status: 401 } });
    expect(state.post).toHaveBeenCalledOnce();
  });
});
