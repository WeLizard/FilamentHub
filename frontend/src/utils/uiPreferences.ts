/**
 * Where the person left the interface: open tab, chosen sub-view.
 * Kept in localStorage, never in cookies — the server has no use for it and
 * cookies would ride along with every request.
 */

const STORAGE_KEY = 'filamenthub.ui-state';

type Scope = string;
type ScopedState = Record<string, string>;

const readAll = (): Record<Scope, ScopedState> => {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === 'object' ? (parsed as Record<Scope, ScopedState>) : {};
  } catch {
    return {};
  }
};

// Two accounts on one machine must not inherit each other's open tabs.
export const uiScopeForUser = (userId: number | null | undefined): Scope =>
  userId != null ? `user:${userId}` : 'anonymous';

export const readUiPreference = (scope: Scope, key: string): string | null => {
  const scoped = readAll()[scope];
  const value = scoped?.[key];
  return typeof value === 'string' ? value : null;
};

export const writeUiPreference = (scope: Scope, key: string, value: string): void => {
  try {
    const all = readAll();
    all[scope] = { ...all[scope], [key]: value };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    // Private mode or a full quota: losing the last open tab is not worth an error.
  }
};

/** Falls back to the default when the stored value is no longer a valid option. */
export const readUiChoice = <T extends string>(
  scope: Scope,
  key: string,
  allowed: readonly T[],
  fallback: T,
): T => {
  const stored = readUiPreference(scope, key);
  return allowed.includes(stored as T) ? (stored as T) : fallback;
};
