interface StoredAttempt {
  fingerprint: string;
  key: string;
}

const memoryAttempts = new Map<string, StoredAttempt>();

const newKey = (prefix: string) => {
  const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  return `${prefix}-${random}`;
};

const readAttempt = (storageKey: string): StoredAttempt | null => {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return memoryAttempts.get(storageKey) ?? null;
    const parsed = JSON.parse(raw) as Partial<StoredAttempt>;
    if (typeof parsed.fingerprint === 'string' && typeof parsed.key === 'string') {
      return { fingerprint: parsed.fingerprint, key: parsed.key };
    }
  } catch {
    // Privacy modes may disable sessionStorage. The in-memory fallback still
    // protects retries while the current page is alive.
  }
  return memoryAttempts.get(storageKey) ?? null;
};

const writeAttempt = (storageKey: string, attempt: StoredAttempt) => {
  memoryAttempts.set(storageKey, attempt);
  try {
    sessionStorage.setItem(storageKey, JSON.stringify(attempt));
  } catch {
    // See readAttempt: the in-memory record is enough for this page lifetime.
  }
};

/**
 * Reuse one idempotency key for an identical action until success is known.
 * A deliberately changed payload starts a new action and therefore gets a new
 * key; a lost response followed by retry keeps the old one.
 */
export function idempotencyKeyForAttempt(
  storageKey: string,
  prefix: string,
  payload: unknown,
): string {
  const fingerprint = JSON.stringify(payload);
  const existing = readAttempt(storageKey);
  if (existing?.fingerprint === fingerprint) return existing.key;

  const attempt = { fingerprint, key: newKey(prefix) };
  writeAttempt(storageKey, attempt);
  return attempt.key;
}

export function clearIdempotencyAttempt(storageKey: string): void {
  memoryAttempts.delete(storageKey);
  try {
    sessionStorage.removeItem(storageKey);
  } catch {
    // Nothing else to clear when storage is unavailable.
  }
}
