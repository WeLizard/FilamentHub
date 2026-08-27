import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { readUiPreference, uiScopeForUser } from '../utils/uiPreferences';
import { useStoredUiChoice } from './useStoredUiChoice';

describe('useStoredUiChoice', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('keeps values separate by account and context key', () => {
    const tabs = ['materials', 'settings'] as const;
    const { result, rerender } = renderHook(
      ({ userId, preferenceKey }) => useStoredUiChoice(
        preferenceKey,
        userId,
        tabs,
        'materials',
      ),
      {
        initialProps: {
          userId: 7,
          preferenceKey: 'companyProfile.tab:12:4',
        },
      },
    );

    act(() => result.current[1]('settings'));
    expect(result.current[0]).toBe('settings');
    expect(readUiPreference(uiScopeForUser(7), 'companyProfile.tab:12:4')).toBe('settings');

    rerender({ userId: 7, preferenceKey: 'companyProfile.tab:15:9' });
    expect(result.current[0]).toBe('materials');

    rerender({ userId: 8, preferenceKey: 'companyProfile.tab:12:4' });
    expect(result.current[0]).toBe('materials');

    rerender({ userId: 7, preferenceKey: 'companyProfile.tab:12:4' });
    expect(result.current[0]).toBe('settings');
  });

  it('restores a value only after a dynamic allowlist contains it', () => {
    window.localStorage.setItem(
      'filamenthub.ui-state',
      JSON.stringify({ 'user:7': { 'profile.orcaSyncDevice': 'device-b' } }),
    );

    const { result, rerender } = renderHook(
      ({ devices }) => useStoredUiChoice(
        'profile.orcaSyncDevice',
        7,
        devices,
        devices[0] ?? '',
      ),
      { initialProps: { devices: [] as string[] } },
    );

    expect(result.current[0]).toBe('');

    rerender({ devices: ['device-a', 'device-b'] });
    expect(result.current[0]).toBe('device-b');

    rerender({ devices: ['device-a'] });
    expect(result.current[0]).toBe('device-a');
  });
});
