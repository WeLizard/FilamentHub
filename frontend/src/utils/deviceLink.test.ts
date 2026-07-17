import { describe, expect, it } from 'vitest';
import {
  DEVICE_LINK_ACTIVE_MS,
  DEVICE_LINK_DELAYED_MS,
  formatLastSeen,
  getDeviceLinkState,
} from './deviceLink';

const NOW = Date.parse('2026-07-17T12:00:00Z');
const iso = (msAgo: number) => new Date(NOW - msAgo).toISOString();

describe('getDeviceLinkState', () => {
  it('is never without a timestamp', () => {
    expect(getDeviceLinkState(null, NOW)).toBe('never');
  });

  it('is active within the active window', () => {
    expect(getDeviceLinkState(iso(0), NOW)).toBe('active');
    expect(getDeviceLinkState(iso(DEVICE_LINK_ACTIVE_MS - 1), NOW)).toBe('active');
  });

  it('is delayed between the windows', () => {
    expect(getDeviceLinkState(iso(DEVICE_LINK_ACTIVE_MS), NOW)).toBe('delayed');
    expect(getDeviceLinkState(iso(DEVICE_LINK_DELAYED_MS - 1), NOW)).toBe('delayed');
  });

  it('is inactive past the delayed window — not "printer offline"', () => {
    expect(getDeviceLinkState(iso(DEVICE_LINK_DELAYED_MS), NOW)).toBe('inactive');
    expect(getDeviceLinkState(iso(86_400_000), NOW)).toBe('inactive');
  });
});

describe('formatLastSeen', () => {
  const t = (key: string, options?: Record<string, unknown>) =>
    options?.count !== undefined ? `${key}:${options.count}` : key;

  it('handles never / minutes / hours buckets', () => {
    expect(formatLastSeen(null, t, 'ru', NOW)).toBe('deviceLink.never');
    expect(formatLastSeen(iso(30_000), t, 'ru', NOW)).toBe('deviceLink.time.ltMinute');
    expect(formatLastSeen(iso(5 * 60_000), t, 'ru', NOW)).toBe('deviceLink.time.minutesAgo:5');
    expect(formatLastSeen(iso(3 * 3_600_000), t, 'ru', NOW)).toBe('deviceLink.time.hoursAgo:3');
  });

  it('falls back to a locale date beyond a day', () => {
    const result = formatLastSeen(iso(3 * 86_400_000), t, 'en', NOW);
    expect(result).not.toContain('deviceLink');
  });
});
