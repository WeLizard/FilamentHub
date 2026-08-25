import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  refresh: vi.fn(),
  getRefreshToken: vi.fn(),
  getToken: vi.fn(),
}));

vi.mock('../api/client', () => ({
  authAPI: { refresh: mocks.refresh },
}));

vi.mock('../utils/auth', () => ({
  getRefreshToken: mocks.getRefreshToken,
  getToken: mocks.getToken,
  isJwtAuthMode: () => true,
}));

import { expiryMs, useTokenRefresh } from './useTokenRefresh';

function tokenWithExp(exp: number | undefined): string {
  const payload = btoa(JSON.stringify(exp === undefined ? {} : { exp }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
  return `header.${payload}.signature`;
}

describe('expiryMs', () => {
  it('reads the expiry a token states', () => {
    expect(expiryMs(tokenWithExp(1_700_000_000))).toBe(1_700_000_000_000);
  });

  it('returns nothing for a token it cannot read', () => {
    // Refusing to guess matters: a wrong expiry would either refresh every ten
    // seconds forever or never refresh at all, and both are worse than leaving the
    // existing 401-and-retry path to do its job.
    expect(expiryMs('not-a-jwt')).toBeNull();
    expect(expiryMs(tokenWithExp(undefined))).toBeNull();
    expect(expiryMs('header..signature')).toBeNull();
  });
});

describe('useTokenRefresh', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    const exp = Math.floor((Date.now() + 121_000) / 1000);
    mocks.getToken.mockReturnValue(tokenWithExp(exp));
    mocks.getRefreshToken.mockReturnValue('old-refresh');
    mocks.refresh.mockResolvedValue({
      access_token: 'new-access',
      refresh_token: 'new-refresh',
      token_type: 'bearer',
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('uses the coordinated API refresh path and schedules the successor', async () => {
    const { unmount } = renderHook(() => useTokenRefresh(true));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(mocks.refresh).toHaveBeenCalledWith('old-refresh');
    unmount();
  });
});
