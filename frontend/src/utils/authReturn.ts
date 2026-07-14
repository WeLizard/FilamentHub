const AUTH_RETURN_TO_KEY = 'fh_auth_return_to';

function isSafeReturnPath(path: string): boolean {
  return path.startsWith('/') && !path.startsWith('//') && !path.includes('\0');
}

export function rememberAuthReturnTo(path?: string): void {
  if (typeof window === 'undefined') return;
  const candidate = path ?? `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (!isSafeReturnPath(candidate)) return;
  try {
    window.sessionStorage.setItem(AUTH_RETURN_TO_KEY, candidate);
  } catch {
    // Storage can be unavailable in embedded WebViews. The current route is
    // still preserved for password login because the modal does not navigate.
  }
}

export function consumeAuthReturnTo(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const candidate = window.sessionStorage.getItem(AUTH_RETURN_TO_KEY);
    window.sessionStorage.removeItem(AUTH_RETURN_TO_KEY);
    return candidate && isSafeReturnPath(candidate) ? candidate : null;
  } catch {
    return null;
  }
}
