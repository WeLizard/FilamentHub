// After a release an open tab still names the previous build's files. Its next
// lazy page then fails to load and the reader lands on the error screen until
// they reload by hand. Vite reports that failure as `vite:preloadError`; one
// reload brings the current build. The time guard stops a loop when the file is
// missing for another reason.
const RELOADED_AT_KEY = 'fh_stale_build_reloaded_at';
const RELOAD_GUARD_MS = 60_000;

export function shouldReloadForStaleBuild(storage: Storage, now: number): boolean {
  try {
    const last = Number(storage.getItem(RELOADED_AT_KEY) ?? 0);
    if (now - last < RELOAD_GUARD_MS) return false;
    storage.setItem(RELOADED_AT_KEY, String(now));
    return true;
  } catch {
    // Without storage the guard cannot hold, so do not risk a reload loop.
    return false;
  }
}

export function installStaleBuildReload(): void {
  window.addEventListener('vite:preloadError', (event) => {
    if (!shouldReloadForStaleBuild(window.sessionStorage, Date.now())) return;
    // The reload replaces the failed navigation; without this the error also
    // reaches the error screen for a moment.
    event.preventDefault();
    window.location.reload();
  });
}
