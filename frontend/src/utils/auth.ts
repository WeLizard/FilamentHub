/**
 * Authentication utilities — dual cookie/jwt strategy.
 *
 * Modes (VITE_AUTH_WEB_MODE):
 *  - "jwt"    — tokens in localStorage, Authorization header (default)
 *  - "cookie" — httpOnly cookie set by backend, CSRF token in header
 *  - "dual"   — backend sets both cookie AND returns JWT; web uses cookies,
 *               OrcaSlicer embedded WebView uses JWT (no cookie support in CEF)
 *
 * OrcaSlicer detection: window.filamenthub (C++ bridge) or window.wx.postMessage.
 * When embedded, tokens are always stored locally regardless of mode,
 * because the WebView cannot rely on browser cookie handling.
 */

import { safeStorage } from './storage';

const AUTH_WEB_MODE = (import.meta.env.VITE_AUTH_WEB_MODE || 'jwt').toLowerCase();

export const isCookieAuthMode = (): boolean => {
  return AUTH_WEB_MODE === 'cookie' || AUTH_WEB_MODE === 'dual';
};

export const isJwtAuthMode = (): boolean => {
  return AUTH_WEB_MODE === 'jwt' || AUTH_WEB_MODE === 'dual';
};

export const isOrcaEmbedded = (): boolean => {
  if (typeof window === 'undefined') {
    return false;
  }
  // NB: window.filamenthub may be a stub the SPA itself creates (App.tsx adds a
  // `navigate` helper, useOrcaSlicerNotifications adds `showNotification`), so its
  // mere existence does NOT mean we run inside the OrcaSlicer WebView. Detect the
  // real C++ bridge by a natively-injected method that the SPA never adds, or by
  // the wx message channel. Otherwise every plain browser is mistaken for the
  // embedded WebView and falls back to localStorage token storage, defeating
  // cookie auth on the web.
  return Boolean(
    window.filamenthub?.importProfile ||
    window.filamenthub?.sendLoginSuccess ||
    window.wx?.postMessage,
  );
};

const canUseLocalTokenStorage = (): boolean => {
  if (!isCookieAuthMode()) {
    return true;
  }
  return isOrcaEmbedded();
};

export const shouldPersistTokensLocally = (): boolean => {
  return canUseLocalTokenStorage();
};

// Доступ к токенам — только через safeStorage: в iframe плагина OrcaSlicer
// (top=file://) прямое обращение к localStorage кидает SecurityError, и без
// fallback падал бы каждый API-запрос ещё в интерсепторе (client.ts).
export const getToken = (): string | null => {
  if (!canUseLocalTokenStorage()) {
    return null;
  }
  return safeStorage.get('access_token');
};

export const getRefreshToken = (): string | null => {
  if (!canUseLocalTokenStorage()) {
    return null;
  }
  return safeStorage.get('refresh_token');
};

export const setToken = (token: string): void => {
  if (!canUseLocalTokenStorage()) {
    return;
  }
  safeStorage.set('access_token', token);
};

export const setUserId = (userId: number): void => {
  if (!canUseLocalTokenStorage()) {
    return;
  }
  safeStorage.set('user_id', userId.toString());
};

export const getUserId = (): number | null => {
  if (!canUseLocalTokenStorage()) {
    return null;
  }
  const userId = safeStorage.get('user_id');
  return userId ? parseInt(userId, 10) : null;
};

export const removeUserId = (): void => {
  safeStorage.remove('user_id');
};

export const setRefreshToken = (token: string): void => {
  if (!canUseLocalTokenStorage()) {
    return;
  }
  safeStorage.set('refresh_token', token);
};

export const removeToken = (): void => {
  safeStorage.remove('access_token');
  safeStorage.remove('refresh_token');
  removeUserId();
};

export const isAuthenticated = (): boolean => {
  return !!getToken();
};

export const getCookieValue = (name: string): string | null => {
  if (typeof document === 'undefined') {
    return null;
  }
  const escapedName = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = document.cookie.match(new RegExp(`(?:^|; )${escapedName}=([^;]*)`));
  if (!match) {
    return null;
  }
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
};

export const getCsrfToken = (): string | null => {
  return getCookieValue(import.meta.env.VITE_AUTH_CSRF_COOKIE_NAME || 'fh_csrf_token');
};

export const clearLegacyLocalAuthStateIfNeeded = (): void => {
  if (isCookieAuthMode() && !isOrcaEmbedded()) {
    removeToken();
  }
};
