import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { readUiPreference, uiScopeForUser } from '../utils/uiPreferences';
import { useStoredViewMode } from './useStoredViewMode';

describe('useStoredViewMode', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('restores each account view without leaking it to another account', () => {
    const { result, rerender } = renderHook(
      ({ userId }) => useStoredViewMode('profile.presetsView', userId),
      { initialProps: { userId: 7 } },
    );

    expect(result.current[0]).toBe('grid');

    act(() => result.current[1]('list'));

    expect(result.current[0]).toBe('list');
    expect(readUiPreference(uiScopeForUser(7), 'profile.presetsView')).toBe('list');

    rerender({ userId: 8 });
    expect(result.current[0]).toBe('grid');

    rerender({ userId: 7 });
    expect(result.current[0]).toBe('list');
  });

  it('falls back when a stored value is no longer a supported mode', () => {
    window.localStorage.setItem(
      'filamenthub.ui-state',
      JSON.stringify({ 'user:7': { 'profile.presetsView': 'tiles' } }),
    );

    const { result } = renderHook(() => useStoredViewMode('profile.presetsView', 7));

    expect(result.current[0]).toBe('grid');
  });
});
