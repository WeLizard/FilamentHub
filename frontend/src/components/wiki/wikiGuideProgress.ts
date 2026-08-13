export const WIKI_GUIDE_PROGRESS_STORAGE_KEY = 'filamenthub:wiki-guide-progress:v1';
export const WIKI_GUIDE_PROGRESS_EVENT = 'filamenthub:wiki-guide-progress-changed';

type WikiGuideProgress = Record<string, string>;

function getStorage(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function readProgress(storage: Storage | null = getStorage()): WikiGuideProgress {
  if (!storage) return {};
  try {
    const parsed = JSON.parse(storage.getItem(WIKI_GUIDE_PROGRESS_STORAGE_KEY) ?? '{}');
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>).filter(
        ([key, value]) => key.length > 0 && typeof value === 'string',
      ),
    ) as WikiGuideProgress;
  } catch {
    return {};
  }
}

export function getCompletedWikiGuideIds(storage: Storage | null = getStorage()): Set<string> {
  return new Set(Object.keys(readProgress(storage)));
}

export function markWikiGuideCompleted(
  guideId: string,
  storage: Storage | null = getStorage(),
): void {
  const normalizedId = guideId.trim();
  if (!storage || !/^[a-z0-9:_-]{1,96}$/i.test(normalizedId)) return;

  const progress = readProgress(storage);
  progress[normalizedId] = new Date().toISOString();

  try {
    storage.setItem(WIKI_GUIDE_PROGRESS_STORAGE_KEY, JSON.stringify(progress));
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent(WIKI_GUIDE_PROGRESS_EVENT, {
        detail: { guideId: normalizedId },
      }));
    }
  } catch {
    // Progress is a convenience. A blocked or full storage must not break the guide.
  }
}

export function mergeCompletedWikiGuideIds(
  guideIds: Iterable<string>,
  storage: Storage | null = getStorage(),
): Set<string> {
  if (!storage) return new Set();
  const progress = readProgress(storage);
  const completedAt = new Date().toISOString();
  for (const rawGuideId of guideIds) {
    const guideId = rawGuideId.trim();
    if (/^[a-z0-9:_-]{1,96}$/i.test(guideId) && !progress[guideId]) {
      progress[guideId] = completedAt;
    }
  }
  try {
    storage.setItem(WIKI_GUIDE_PROGRESS_STORAGE_KEY, JSON.stringify(progress));
  } catch {
    // Reading progress remains possible even when browser storage is blocked.
  }
  return new Set(Object.keys(progress));
}
