import { useCallback, useState } from 'react';

import {
  readUiChoice,
  uiScopeForUser,
  writeUiPreference,
} from '../utils/uiPreferences';

interface StoredChoiceState {
  preferenceKey: string;
  scope: string;
  value: string;
}

/**
 * Remembers one value from a caller-provided allowlist.
 *
 * The scope and key travel with the in-memory state so switching accounts,
 * brands or organizations cannot briefly write the previous context's value
 * into the new one. Dynamic allowlists also make stale countries and device
 * fingerprints fall back without ever being selected.
 */
export function useStoredUiChoice<T extends string>(
  preferenceKey: string,
  userId: number | null | undefined,
  allowedValues: readonly T[],
  fallback: T,
): [T, (value: T) => void] {
  const scope = uiScopeForUser(userId);
  const [state, setState] = useState<StoredChoiceState>(() => ({
    preferenceKey,
    scope,
    value: readUiChoice(scope, preferenceKey, allowedValues, fallback),
  }));

  const stateMatchesContext = state.scope === scope
    && state.preferenceKey === preferenceKey
    && allowedValues.includes(state.value as T);
  const value = stateMatchesContext
    ? state.value as T
    : readUiChoice(scope, preferenceKey, allowedValues, fallback);

  const setValue = useCallback((nextValue: T) => {
    if (!allowedValues.includes(nextValue)) return;
    writeUiPreference(scope, preferenceKey, nextValue);
    setState({ preferenceKey, scope, value: nextValue });
  }, [allowedValues, preferenceKey, scope]);

  return [value, setValue];
}
