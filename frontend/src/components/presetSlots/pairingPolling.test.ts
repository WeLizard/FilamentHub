import { describe, expect, it } from 'vitest';
import { edgePairingRefetchInterval } from './EdgeConnectionSetup';
import { bambuPairingRefetchInterval } from './adapters/bambu';
import { octoPrintPairingRefetchInterval } from './adapters/octoprint';
import { isPairingAccessDenied, retryPairingStatusQuery } from './pairingPolling';

const now = Date.parse('2026-09-05T12:00:00Z');
const deadline = Date.parse('2026-09-05T12:10:00Z');
const activePairingIntervals = [
  (error: unknown) => edgePairingRefetchInterval(
    error,
    { pairing_expires_at: '2026-09-05T12:10:00Z', paired: false },
    deadline,
    now,
  ),
  (error: unknown) => bambuPairingRefetchInterval(
    error,
    { paired: false, last_seen_at: null },
    true,
    deadline,
    now,
  ),
  (error: unknown) => octoPrintPairingRefetchInterval(
    error,
    { paired: false },
    'FH-PAIRING-CODE',
    '2026-09-05T12:10:00Z',
    now,
  ),
];

describe('pairing status polling', () => {
  it('stops every active pairing timer and automatic retry after access is denied', () => {
    for (const status of [401, 403]) {
      const error = { response: { status } };
      expect(isPairingAccessDenied(error)).toBe(true);
      expect(retryPairingStatusQuery(0, error)).toBe(false);
      expect(activePairingIntervals.map((interval) => interval(error))).toEqual([
        false,
        false,
        false,
      ]);
    }
  });

  it('keeps the previous one-retry budget and polling interval for temporary failures', () => {
    for (const error of [new Error('network unavailable'), { response: { status: 503 } }]) {
      expect(isPairingAccessDenied(error)).toBe(false);
      expect(retryPairingStatusQuery(0, error)).toBe(true);
      expect(retryPairingStatusQuery(1, error)).toBe(false);
      expect(activePairingIntervals.map((interval) => interval(error))).toEqual([
        5_000,
        5_000,
        5_000,
      ]);
    }
  });

  it('resumes an explicit active pairing after a successful refetch and still stops at terminal state', () => {
    expect(activePairingIntervals.map((interval) => interval(null))).toEqual([
      5_000,
      5_000,
      5_000,
    ]);
    expect(edgePairingRefetchInterval(null, { paired: false }, now - 1, now)).toBe(false);
    expect(bambuPairingRefetchInterval(
      null,
      { paired: true, last_seen_at: '2026-09-05T11:59:00Z' },
      false,
      deadline,
      now,
    )).toBe(false);
    expect(octoPrintPairingRefetchInterval(
      null,
      { paired: true },
      'FH-PAIRING-CODE',
      '2026-09-05T12:10:00Z',
      now,
    )).toBe(false);
  });
});
