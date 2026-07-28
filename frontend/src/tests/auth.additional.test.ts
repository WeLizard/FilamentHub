import { beforeEach, describe, expect, it, vi } from 'vitest';

function mockEnv(vars: Record<string, string>) {
  vi.stubEnv('VITE_AUTH_WEB_MODE', vars.VITE_AUTH_WEB_MODE ?? '');
  vi.stubEnv('VITE_AUTH_CSRF_COOKIE_NAME', vars.VITE_AUTH_CSRF_COOKIE_NAME ?? '');
}

async function loadAuth() {
  vi.resetModules();
  return import('../utils/auth');
}

describe('auth.ts additional coverage', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllEnvs();
    Object.defineProperty(window, 'filamenthub', { value: undefined, writable: true, configurable: true });
    Object.defineProperty(window, 'wx', { value: undefined, writable: true, configurable: true });
  });

  it('detects Orca embedding via window.wx.postMessage', async () => {
    (window as any).wx = { postMessage: vi.fn() };
    const auth = await loadAuth();
    expect(auth.isOrcaEmbedded()).toBe(true);
  });

  it('persists tokens in cookie mode when embedded in Orca', async () => {
    mockEnv({ VITE_AUTH_WEB_MODE: 'cookie' });
    (window as any).filamenthub = { sendLoginSuccess: vi.fn() };

    const auth = await loadAuth();
    expect(auth.shouldPersistTokensLocally()).toBe(true);

    auth.setToken('embedded-cookie-token');
    expect(auth.getToken()).toBe('embedded-cookie-token');
  });

  it('uses custom csrf cookie name in getCsrfToken', async () => {
    mockEnv({ VITE_AUTH_CSRF_COOKIE_NAME: 'my_csrf' });
    Object.defineProperty(document, 'cookie', {
      value: 'my_csrf=custom-token; other=1',
      writable: true,
      configurable: true,
    });

    const auth = await loadAuth();
    expect(auth.getCsrfToken()).toBe('custom-token');
  });

  it('does not clear legacy local auth state for Orca in cookie mode', async () => {
    mockEnv({ VITE_AUTH_WEB_MODE: 'cookie' });
    (window as any).filamenthub = { sendLoginSuccess: vi.fn() };

    localStorage.setItem('access_token', 'keep-me');
    localStorage.setItem('refresh_token', 'keep-me-too');

    const auth = await loadAuth();
    auth.clearLegacyLocalAuthStateIfNeeded();

    expect(localStorage.getItem('access_token')).toBe('keep-me');
    expect(localStorage.getItem('refresh_token')).toBe('keep-me-too');
  });
});
