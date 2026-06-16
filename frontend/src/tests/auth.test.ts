import { describe, it, expect, beforeEach, vi } from 'vitest';

// We need to mock import.meta.env before importing the module,
// so we use dynamic imports with vi.resetModules() between tests.

function mockEnv(vars: Record<string, string>) {
  vi.stubEnv('VITE_AUTH_WEB_MODE', vars.VITE_AUTH_WEB_MODE ?? '');
  vi.stubEnv('VITE_AUTH_CSRF_COOKIE_NAME', vars.VITE_AUTH_CSRF_COOKIE_NAME ?? '');
}

async function loadAuth() {
  vi.resetModules();
  return import('../utils/auth');
}

describe('auth.ts', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllEnvs();
    Object.defineProperty(window, 'filamenthub', { value: undefined, writable: true, configurable: true });
    Object.defineProperty(window, 'wx', { value: undefined, writable: true, configurable: true });
  });

  describe('mode detection', () => {
    it('defaults to jwt mode when env is not set', async () => {
      mockEnv({});
      const auth = await loadAuth();
      expect(auth.isJwtAuthMode()).toBe(true);
      expect(auth.isCookieAuthMode()).toBe(false);
    });

    it('cookie mode', async () => {
      mockEnv({ VITE_AUTH_WEB_MODE: 'cookie' });
      const auth = await loadAuth();
      expect(auth.isCookieAuthMode()).toBe(true);
      expect(auth.isJwtAuthMode()).toBe(false);
    });

    it('dual mode enables both', async () => {
      mockEnv({ VITE_AUTH_WEB_MODE: 'dual' });
      const auth = await loadAuth();
      expect(auth.isCookieAuthMode()).toBe(true);
      expect(auth.isJwtAuthMode()).toBe(true);
    });
  });

  describe('orca embedded detection', () => {
    it('returns false by default', async () => {
      const auth = await loadAuth();
      expect(auth.isOrcaEmbedded()).toBe(false);
    });

    it('detects the OrcaSlicer bridge by a native method', async () => {
      // The real C++ bridge injects native methods like importProfile.
      (window as any).filamenthub = { importProfile: vi.fn() };
      const auth = await loadAuth();
      expect(auth.isOrcaEmbedded()).toBe(true);
    });

    it('ignores a bare window.filamenthub stub without a native method', async () => {
      // App.tsx attaches a `navigate` helper to window.filamenthub in every
      // browser; that stub must NOT be mistaken for the embedded WebView.
      (window as any).filamenthub = { navigate: vi.fn() };
      const auth = await loadAuth();
      expect(auth.isOrcaEmbedded()).toBe(false);
    });

    it('detects the WeChat-style window.wx bridge', async () => {
      (window as any).wx = { postMessage: vi.fn() };
      const auth = await loadAuth();
      expect(auth.isOrcaEmbedded()).toBe(true);
    });
  });

  describe('token storage in jwt mode', () => {
    it('stores and retrieves token', async () => {
      mockEnv({ VITE_AUTH_WEB_MODE: 'jwt' });
      const auth = await loadAuth();
      auth.setToken('test-token-123');
      expect(auth.getToken()).toBe('test-token-123');
      expect(auth.isAuthenticated()).toBe(true);
    });

    it('stores and retrieves refresh token', async () => {
      mockEnv({ VITE_AUTH_WEB_MODE: 'jwt' });
      const auth = await loadAuth();
      auth.setRefreshToken('refresh-456');
      expect(auth.getRefreshToken()).toBe('refresh-456');
    });

    it('removeToken clears all auth data', async () => {
      mockEnv({ VITE_AUTH_WEB_MODE: 'jwt' });
      const auth = await loadAuth();
      auth.setToken('t');
      auth.setRefreshToken('r');
      auth.setUserId(42);
      auth.removeToken();
      expect(auth.getToken()).toBeNull();
      expect(auth.getRefreshToken()).toBeNull();
      expect(auth.getUserId()).toBeNull();
    });
  });

  describe('token storage in cookie mode (non-orca)', () => {
    it('does not store tokens locally', async () => {
      mockEnv({ VITE_AUTH_WEB_MODE: 'cookie' });
      const auth = await loadAuth();
      auth.setToken('should-not-persist');
      expect(auth.getToken()).toBeNull();
      expect(localStorage.getItem('access_token')).toBeNull();
    });

    it('shouldPersistTokensLocally returns false', async () => {
      mockEnv({ VITE_AUTH_WEB_MODE: 'cookie' });
      const auth = await loadAuth();
      expect(auth.shouldPersistTokensLocally()).toBe(false);
    });
  });

  describe('userId', () => {
    it('stores and retrieves numeric user id', async () => {
      mockEnv({ VITE_AUTH_WEB_MODE: 'jwt' });
      const auth = await loadAuth();
      auth.setUserId(99);
      expect(auth.getUserId()).toBe(99);
    });

    it('returns null when not set', async () => {
      const auth = await loadAuth();
      expect(auth.getUserId()).toBeNull();
    });
  });

  describe('getCookieValue', () => {
    it('parses cookie from document.cookie', async () => {
      Object.defineProperty(document, 'cookie', {
        value: 'fh_csrf_token=abc123; session=xyz',
        writable: true,
        configurable: true,
      });
      const auth = await loadAuth();
      expect(auth.getCookieValue('fh_csrf_token')).toBe('abc123');
      expect(auth.getCookieValue('session')).toBe('xyz');
      expect(auth.getCookieValue('nonexistent')).toBeNull();
    });
  });

  describe('buildAuthenticatedUploadUrl', () => {
    it('appends token when authenticated', async () => {
      mockEnv({ VITE_AUTH_WEB_MODE: 'jwt' });
      const auth = await loadAuth();
      auth.setToken('tok');
      const url = auth.buildAuthenticatedUploadUrl('/avatars/pic.png');
      expect(url).toBe('/api/v1/uploads/avatars/pic.png?token=tok');
    });

    it('returns plain url when no token', async () => {
      mockEnv({ VITE_AUTH_WEB_MODE: 'cookie' });
      const auth = await loadAuth();
      const url = auth.buildAuthenticatedUploadUrl('avatars/pic.png');
      expect(url).toBe('/api/v1/uploads/avatars/pic.png');
    });
  });

  describe('clearLegacyLocalAuthStateIfNeeded', () => {
    it('clears localStorage in cookie mode (non-orca)', async () => {
      mockEnv({ VITE_AUTH_WEB_MODE: 'cookie' });
      localStorage.setItem('access_token', 'old');
      localStorage.setItem('refresh_token', 'old-r');
      const auth = await loadAuth();
      auth.clearLegacyLocalAuthStateIfNeeded();
      expect(localStorage.getItem('access_token')).toBeNull();
      expect(localStorage.getItem('refresh_token')).toBeNull();
    });
  });
});
