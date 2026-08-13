import { beforeEach, describe, expect, it } from 'vitest';

import {
  clearIdempotencyAttempt,
  idempotencyKeyForAttempt,
} from './idempotencyAttempt';

describe('idempotencyKeyForAttempt', () => {
  const storageKey = 'fh:test:print-job';

  beforeEach(() => {
    clearIdempotencyAttempt(storageKey);
  });

  it('reuses a key after an uncertain response but replaces it for a new action', () => {
    const first = idempotencyKeyForAttempt(storageKey, 'web', { title: 'Cube' });
    const retry = idempotencyKeyForAttempt(storageKey, 'web', { title: 'Cube' });
    const edited = idempotencyKeyForAttempt(storageKey, 'web', { title: 'Vase' });

    expect(retry).toBe(first);
    expect(edited).not.toBe(first);

    clearIdempotencyAttempt(storageKey);
    expect(idempotencyKeyForAttempt(storageKey, 'web', { title: 'Vase' })).not.toBe(edited);
  });
});
