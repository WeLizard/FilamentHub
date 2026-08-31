import { describe, expect, it } from 'vitest';
import {
  DEVICE_LINK_ACTIVE_MS,
  DEVICE_LINK_DELAYED_MS,
  formatLastSeen,
  getDeviceLinkState,
  latestDeviceContact,
  latestFreshStatusConnector,
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

  it('keeps an on-demand provider ready between explicit requests', () => {
    expect(getDeviceLinkState(iso(0), NOW, 'on_demand')).toBe('ready');
    expect(getDeviceLinkState(iso(7 * 86_400_000), NOW, 'on_demand')).toBe('ready');
    expect(getDeviceLinkState(null, NOW, 'on_demand')).toBe('never');
  });
});

describe('latestDeviceContact', () => {
  it('uses the freshest valid printer or connector contact', () => {
    expect(latestDeviceContact(
      '2026-07-17T11:00:00Z',
      '2026-07-17T11:59:00Z',
    )).toBe('2026-07-17T11:59:00Z');
    expect(latestDeviceContact(null, 'invalid')).toBeNull();
  });
});

describe('latestFreshStatusConnector', () => {
  it('ignores stale status and picks the newest fresh active connector', () => {
    const connectors = [
      {
        id: 1,
        active: true,
        last_seen_at: iso(1_000),
        status_observation: {
          state: 'printing',
          received_at: iso(DEVICE_LINK_DELAYED_MS),
        },
      },
      {
        id: 2,
        active: true,
        last_seen_at: iso(60_000),
        status_observation: { state: 'idle', received_at: iso(60_000) },
      },
      {
        id: 3,
        active: false,
        last_seen_at: iso(1_000),
        status_observation: { state: 'failed', received_at: iso(1_000) },
      },
    ];

    expect(latestFreshStatusConnector(connectors, NOW)?.id).toBe(2);
    expect(latestFreshStatusConnector([connectors[0]], NOW)).toBeNull();
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
