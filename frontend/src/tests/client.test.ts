import { beforeEach, describe, expect, it, vi } from 'vitest';

const authMocks = vi.hoisted(() => ({
  getCsrfToken: vi.fn(() => null),
  getRefreshToken: vi.fn(() => 'refresh-token'),
  getToken: vi.fn(() => localStorage.getItem('access_token')),
  isCookieAuthMode: vi.fn(() => false),
  isJwtAuthMode: vi.fn(() => true),
  isOrcaEmbedded: vi.fn(() => false),
  removeToken: vi.fn(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user_id');
  }),
  setToken: vi.fn((token: string) => {
    localStorage.setItem('access_token', token);
  }),
  shouldPersistTokensLocally: vi.fn(() => true),
}));

const axiosState = vi.hoisted(() => {
  const state: {
    requestFulfilled: ((config: any) => any) | null;
    responseRejected: ((error: any) => Promise<any>) | null;
    apiInstance: any;
    create: any;
    post: any;
    get: any;
  } = {
    requestFulfilled: null,
    responseRejected: null,
    apiInstance: null,
    create: vi.fn(),
    post: vi.fn(),
    get: vi.fn(),
  };

  const apiInstance: any = vi.fn((config: any) => Promise.resolve({ data: { ok: true }, config }));
  apiInstance.get = vi.fn();
  apiInstance.post = vi.fn();
  apiInstance.patch = vi.fn();
  apiInstance.delete = vi.fn();
  apiInstance.interceptors = {
    request: {
      use: vi.fn((fulfilled: (config: any) => any) => {
        state.requestFulfilled = fulfilled;
        return 0;
      }),
    },
    response: {
      use: vi.fn((_: (response: any) => any, rejected: (error: any) => Promise<any>) => {
        state.responseRejected = rejected;
        return 0;
      }),
    },
  };

  state.apiInstance = apiInstance;
  state.create.mockReturnValue(apiInstance);

  return state;
});

vi.mock('../utils/auth', () => authMocks);

vi.mock('axios', () => ({
  default: {
    create: axiosState.create,
    post: axiosState.post,
    get: axiosState.get,
  },
}));

async function loadClientModule() {
  vi.resetModules();
  return import('../api/client');
}

describe('api/client interceptors', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    axiosState.requestFulfilled = null;
    axiosState.responseRejected = null;

    authMocks.getRefreshToken.mockReturnValue('refresh-token');
    authMocks.isCookieAuthMode.mockReturnValue(false);
    authMocks.isJwtAuthMode.mockReturnValue(true);
    authMocks.shouldPersistTokensLocally.mockReturnValue(true);
  });

  it('adds Authorization header in request interceptor', async () => {
    localStorage.setItem('access_token', 'access-123');
    await loadClientModule();

    const requestInterceptor = axiosState.requestFulfilled;
    expect(requestInterceptor).toBeTypeOf('function');

    const config = { headers: {}, method: 'get' };
    const updatedConfig = requestInterceptor!(config);

    expect(updatedConfig.headers.Authorization).toBe('Bearer access-123');
  });

  it('triggers refresh flow on 401 response', async () => {
    localStorage.setItem('access_token', 'expired-token');
    localStorage.setItem('refresh_token', 'refresh-token');

    await loadClientModule();

    axiosState.post.mockResolvedValueOnce({
      data: { access_token: 'new-token' },
    });

    const responseRejected = axiosState.responseRejected;
    expect(responseRejected).toBeTypeOf('function');

    await responseRejected!({
      response: { status: 401 },
      config: { url: '/protected', method: 'get', headers: {} },
    });

    expect(axiosState.post).toHaveBeenCalledWith(
      '/api/v1/auth/refresh',
      { refresh_token: 'refresh-token' },
      expect.objectContaining({ withCredentials: false })
    );
  });

  it('retries original request after successful refresh', async () => {
    localStorage.setItem('access_token', 'expired-token');
    localStorage.setItem('refresh_token', 'refresh-token');

    await loadClientModule();

    axiosState.post.mockResolvedValueOnce({
      data: { access_token: 'new-token' },
    });
    axiosState.apiInstance.mockResolvedValueOnce({ data: { retried: true } });

    const originalRequest: { url: string; method: string; headers: Record<string, string> } = {
      url: '/protected',
      method: 'get',
      headers: {},
    };
    const responseRejected = axiosState.responseRejected;

    const result = await responseRejected!({
      response: { status: 401 },
      config: originalRequest,
    });

    expect(localStorage.getItem('access_token')).toBe('new-token');
    expect(originalRequest.headers.Authorization).toBe('Bearer new-token');
    expect(axiosState.apiInstance).toHaveBeenCalledWith(originalRequest);
    expect(result).toEqual({ data: { retried: true } });
  });

  it('calls logout logic when refresh fails', async () => {
    localStorage.setItem('access_token', 'expired-token');
    localStorage.setItem('refresh_token', 'refresh-token');

    await loadClientModule();

    axiosState.post.mockRejectedValueOnce(new Error('refresh failed'));

    const responseRejected = axiosState.responseRejected;

    await expect(
      responseRejected!({
        response: { status: 401 },
        config: { url: '/protected', method: 'get', headers: {} },
      })
    ).rejects.toThrow('refresh failed');

    expect(authMocks.removeToken).toHaveBeenCalledTimes(1);
  });
});

describe('admin email uploads', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('sends a new letter as multipart so the files survive', async () => {
    const { adminCommunicationsAPI } = await loadClientModule();
    axiosState.apiInstance.post.mockResolvedValueOnce({ data: {} });

    await adminCommunicationsAPI.createEmailThread({
      to: 'team@example.com',
      subject: 'Subject',
      body: 'Body',
      sender_profile: 'support',
      language: 'en',
      idempotency_key: 'email.create.1',
      attachments: [new File(['<html></html>'], 'application.html', { type: 'text/html' })],
    });

    const [, payload, config] = axiosState.apiInstance.post.mock.calls[0];
    expect(payload).toBeInstanceOf(FormData);
    expect((payload as FormData).getAll('attachments')).toHaveLength(1);
    expect((payload as FormData).get('language')).toBe('en');
    expect(config.headers['Content-Type']).toBe('multipart/form-data');
  });

  it('sends a reply as multipart so the files survive', async () => {
    const { adminCommunicationsAPI } = await loadClientModule();
    axiosState.apiInstance.post.mockResolvedValueOnce({ data: {} });

    await adminCommunicationsAPI.replyToEmailThread(7, {
      body: 'Body',
      idempotency_key: 'email.reply.1',
      attachments: [new File(['<html></html>'], 'application.html', { type: 'text/html' })],
    });

    const [, payload, config] = axiosState.apiInstance.post.mock.calls[0];
    expect(payload).toBeInstanceOf(FormData);
    expect((payload as FormData).getAll('attachments')).toHaveLength(1);
    expect(config.headers['Content-Type']).toBe('multipart/form-data');
  });
});

describe('SpoolManager CSV uploads', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('sends preview and confirmed import as multipart forms', async () => {
    const { spoolsAPI } = await loadClientModule();
    axiosState.apiInstance.post.mockResolvedValue({ data: {} });
    const file = new File(['csv'], 'spools.csv', { type: 'text/csv' });

    await spoolsAPI.previewSpoolManager(file);
    await spoolsAPI.importSpoolManager(file, ['row-fingerprint']);

    const [, previewPayload, previewConfig] = axiosState.apiInstance.post.mock.calls[0];
    expect(previewPayload).toBeInstanceOf(FormData);
    expect((previewPayload as FormData).get('file')).toBe(file);
    expect(previewConfig.headers['Content-Type']).toBe('multipart/form-data');

    const [, importPayload, importConfig] = axiosState.apiInstance.post.mock.calls[1];
    expect(importPayload).toBeInstanceOf(FormData);
    expect((importPayload as FormData).get('file')).toBe(file);
    expect((importPayload as FormData).get('selected_fingerprints')).toBe(
      '["row-fingerprint"]',
    );
    expect(importConfig.headers['Content-Type']).toBe('multipart/form-data');
  });

  it('sends provider-neutral mapping with generic preview and import', async () => {
    const { spoolsAPI } = await loadClientModule();
    axiosState.apiInstance.post.mockResolvedValue({ data: {} });
    const file = new File(['csv'], 'inventory.csv', { type: 'text/csv' });
    const mapping = {
      fields: {
        spool_name: 'Name',
        remaining_weight: 'Remaining kg',
      },
      units: {
        remaining_weight: 'kg' as const,
      },
    };

    await spoolsAPI.previewImport(file, mapping);
    await spoolsAPI.importFile(file, ['mapped-row'], mapping);

    const [previewUrl, previewPayload] = axiosState.apiInstance.post.mock.calls[0];
    expect(previewUrl).toBe('/spools/import/preview');
    expect((previewPayload as FormData).get('mapping')).toBe(JSON.stringify(mapping));

    const [importUrl, importPayload] = axiosState.apiInstance.post.mock.calls[1];
    expect(importUrl).toBe('/spools/import');
    expect((importPayload as FormData).get('selected_fingerprints')).toBe(
      '["mapped-row"]',
    );
    expect((importPayload as FormData).get('mapping')).toBe(JSON.stringify(mapping));
  });
});

describe('brand material CSV uploads', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('previews first and sends the signed confirmation only on apply', async () => {
    const { filamentImportAPI } = await loadClientModule();
    axiosState.apiInstance.post.mockResolvedValue({ data: {} });
    const file = new File(['csv'], 'materials.csv', { type: 'text/csv' });

    await filamentImportAPI.previewCsv(42, file, 'DE');
    await filamentImportAPI.importCsv(42, file, 'signed-plan', 'DE');

    const [previewUrl, previewPayload, previewConfig] =
      axiosState.apiInstance.post.mock.calls[0];
    expect(previewUrl).toBe('/filament-import/preview');
    expect(previewPayload).toBeInstanceOf(FormData);
    expect((previewPayload as FormData).get('file')).toBe(file);
    expect((previewPayload as FormData).get('confirmation_token')).toBeNull();
    expect(previewConfig.params).toEqual({ brand_id: 42, country: 'DE' });

    const [importUrl, importPayload, importConfig] =
      axiosState.apiInstance.post.mock.calls[1];
    expect(importUrl).toBe('/filament-import');
    expect(importPayload).toBeInstanceOf(FormData);
    expect((importPayload as FormData).get('file')).toBe(file);
    expect((importPayload as FormData).get('confirmation_token')).toBe('signed-plan');
    expect(importConfig.params).toEqual({ brand_id: 42, country: 'DE' });
  });
});
