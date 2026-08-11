import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useOrcaBridgeCapability } from './useOrcaBridgeCapability';

afterEach(() => {
  delete window.filamenthub;
  delete window.wx;
  vi.useRealTimers();
});

describe('useOrcaBridgeCapability', () => {
  it('detects an asynchronously injected bridge and stops steady-state polling', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useOrcaBridgeCapability('exportFilamentPresets'));
    expect(result.current).toBe(false);

    window.filamenthub = { exportFilamentPresets: vi.fn(async () => ({})) };
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current).toBe(true);

    const timerCount = vi.getTimerCount();
    act(() => vi.advanceTimersByTime(60_000));
    expect(vi.getTimerCount()).toBe(timerCount);
  });
});
