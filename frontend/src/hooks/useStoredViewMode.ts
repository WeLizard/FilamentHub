import { useCallback, useState } from 'react';

import type { ViewMode } from '../components/ViewModeToggle';
import {
  readUiChoice,
  uiScopeForUser,
  writeUiPreference,
} from '../utils/uiPreferences';

const VIEW_MODES = ['grid', 'list'] as const;

interface StoredViewModeState {
  scope: string;
  value: ViewMode;
}

export function useStoredViewMode(
  preferenceKey: string,
  userId: number | null | undefined,
  fallback: ViewMode = 'grid',
): [ViewMode, (mode: ViewMode) => void] {
  const scope = uiScopeForUser(userId);
  const [state, setState] = useState<StoredViewModeState>(() => ({
    scope,
    value: readUiChoice(scope, preferenceKey, VIEW_MODES, fallback),
  }));

  // Account changes do not have to remount the whole SPA. Read the new
  // account's preference without first writing the previous account's value.
  const value = state.scope === scope
    ? state.value
    : readUiChoice(scope, preferenceKey, VIEW_MODES, fallback);

  const setValue = useCallback((mode: ViewMode) => {
    writeUiPreference(scope, preferenceKey, mode);
    setState({ scope, value: mode });
  }, [preferenceKey, scope]);

  return [value, setValue];
}
