import { useEffect } from 'react';

import { authAPI } from '../api/client';
import { getRefreshToken, getToken, isJwtAuthMode } from '../utils/auth';

/** Renew the access token shortly before it expires. */
const RENEW_BEFORE_EXPIRY_MS = 2 * 60 * 1000;
/** Never schedule tighter than this, so a clock skew cannot spin the timer. */
const MIN_DELAY_MS = 10 * 1000;

/**
 * Seconds since the epoch this token stops being accepted, if it says so.
 *
 * Exported for tests: a misread expiry either refreshes every ten seconds forever or
 * never refreshes at all, and both are worse than the behaviour this replaces.
 */
export function expiryMs(token: string): number | null {
  const payload = token.split('.')[1];
  if (!payload) return null;
  try {
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    const claims = JSON.parse(json) as { exp?: number };
    return typeof claims.exp === 'number' ? claims.exp * 1000 : null;
  } catch {
    // A token this code cannot read is still a token the server may accept; the
    // interceptor keeps handling it the old way.
    return null;
  }
}

/**
 * Renew the session before it lapses instead of after.
 *
 * Without this the first request made with an expired token fails, the interceptor
 * refreshes and retries, and the person stays signed in — but a 401 is written to the
 * console every time. That noise is not harmless: it is indistinguishable from a real
 * failure, and it hid actual 500s while the CRM was broken.
 *
 * Deliberately outside the interceptors. They remain the safety net, so a timer that
 * never fires — a sleeping tab, an unreadable token — costs nothing beyond the console
 * line it was meant to remove.
 */
export function useTokenRefresh(isAuthenticated: boolean): void {
  useEffect(() => {
    if (!isAuthenticated || !isJwtAuthMode()) return undefined;

    let timer: number | undefined;
    let cancelled = false;

    const schedule = () => {
      const token = getToken();
      const expiresAt = token ? expiryMs(token) : null;
      if (expiresAt === null) return;

      const delay = Math.max(MIN_DELAY_MS, expiresAt - Date.now() - RENEW_BEFORE_EXPIRY_MS);
      timer = window.setTimeout(async () => {
        try {
          const { access_token } = await authAPI.refresh(getRefreshToken());
          if (cancelled || !access_token) return;
          schedule();
        } catch {
          // The interceptor still refreshes on the next 401, which is exactly the
          // behaviour that existed before this hook.
        }
      }, delay);
    };

    schedule();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [isAuthenticated]);
}
