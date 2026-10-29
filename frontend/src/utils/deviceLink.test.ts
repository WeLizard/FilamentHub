import type { ContactChannel } from './deviceLink';
import { describe, expect, it } from 'vitest';
import {
  activeMaterialSystemConnectors,
  connectorChannels,
  DEVICE_LINK_ACTIVE_MS,
  DEVICE_LINK_DELAYED_MS,
  formatLastSeen,
  formatLocalizedList,
  getDeviceLinkState,
  latestDeviceContact,
  latestFreshStatusConnector,
  latestMaterialSystemContact,
  linkFromChannels,
  observationSource,
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

describe('material-system connector summary', () => {
  const connectors = [
    {
      id: 1,
      active: true,
      material_system_id: 21,
      provider: 'bambu',
      transport: 'orca_plugin_lan',
      last_seen_at: iso(DEVICE_LINK_DELAYED_MS),
    },
    {
      id: 2,
      active: true,
      material_system_id: 21,
      provider: 'happy_hare',
      transport: 'edge_agent',
      last_seen_at: iso(30_000),
    },
    {
      id: 3,
      active: false,
      material_system_id: 21,
      provider: 'happy_hare',
      transport: 'moonraker',
      last_seen_at: iso(1_000),
    },
    {
      id: 4,
      active: true,
      material_system_id: 22,
      provider: 'octoprint',
      transport: 'octoprint_plugin',
      last_seen_at: iso(1_000),
    },
  ];

  it('uses every active connector for the system and is independent of array order', () => {
    expect(activeMaterialSystemConnectors(connectors, 21).map((item) => item.id)).toEqual([1, 2]);
    expect(latestMaterialSystemContact(connectors, 21, iso(0))).toBe(iso(30_000));
    expect(latestMaterialSystemContact([...connectors].reverse(), 21, iso(0))).toBe(iso(30_000));
    expect(connectorChannels(activeMaterialSystemConnectors(connectors, 21))).toEqual(['edge', 'orca']);
  });

  it('uses the legacy printer contact only when the system has no connector', () => {
    expect(latestMaterialSystemContact(connectors, 23, iso(20_000))).toBe(iso(20_000));
    expect(latestMaterialSystemContact(connectors, 21, iso(0))).not.toBe(iso(0));
  });
});

describe('observationSource', () => {
  it('maps known sources and keeps unknown identifiers private', () => {
    expect(observationSource('happy_hare_edge')).toBe('happyHareEdge');
    expect(observationSource('edge_happy_hare')).toBe('happyHareEdge');
    expect(observationSource('happy_hare_moonraker')).toBe('happyHareMoonraker');
    expect(observationSource('bambu_lan_mqtt')).toBe('bambuLan');
    expect(observationSource('internal_new_adapter_v9')).toBe('adapter');
  });
});

describe('formatLocalizedList', () => {
  it('uses locale-specific list punctuation', () => {
    expect(formatLocalizedList(['material', 'color'], 'en')).toBe('material and color');
    expect(formatLocalizedList(['材料', '颜色'], 'zh')).toBe('材料和颜色');
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

describe('linkFromChannels', () => {
  const channel = (state: ContactChannel['state'], last: string | null, kind: ContactChannel['kind'] = 'connector'): ContactChannel => ({
    kind, source: 'x', connector_id: null, material_system_id: 1, last_contact_at: last, state, basis: 'heartbeat',
  });

  it('shows the live channel\'s own time and never borrows a fresher time from a silent one', () => {
    const result = linkFromChannels([
      channel('silent', '2026-10-29T10:59:00Z', 'native_spoolman'),
      channel('live', '2026-10-29T09:00:00Z'),
    ]);
    expect(result).toEqual({ state: 'active', lastContactAt: '2026-10-29T09:00:00Z' });
  });

  it('keeps a lost lease as delayed data, not as live', () => {
    expect(linkFromChannels([channel('unknown', '2026-10-29T09:00:00Z', 'native_spoolman')]).state).toBe('delayed');
  });

  it('treats a channel that was never heard from as never connected', () => {
    expect(linkFromChannels([channel('unknown', null), channel('not_configured', null)]).state).toBe('never');
  });
});

describe('linkFromChannels with a degraded or lost link', () => {
  const channel = (state: ContactChannel['state']): ContactChannel => ({
    kind: 'connector', source: 'x', connector_id: 1, material_system_id: 1,
    last_contact_at: '2026-10-29T09:00:00Z', state, basis: 'heartbeat',
  });

  it('tells a live helper with an unreachable printer apart from a dead link', () => {
    expect(linkFromChannels([channel('executor_only')]).state).toBe('executor');
  });

  it('asks for action only when nothing else is live', () => {
    expect(linkFromChannels([channel('needs_action'), channel('silent')]).state).toBe('action');
    expect(linkFromChannels([channel('needs_action'), channel('live')]).state).toBe('active');
  });
});
