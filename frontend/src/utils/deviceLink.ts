/**
 * Adapter-link freshness for user printer devices.
 *
 * `last_seen_at` records the last successful contact of the plugin/adapter
 * (Orca plugin, Happy Hare via the Spoolman-compatible API) with FilamentHub.
 * It says nothing about whether the physical printer is powered on — the UI
 * must present it as the state of the LINK, never as printer online/offline.
 */

import { useEffect, useState } from 'react';

export type DeviceLinkState = 'active' | 'delayed' | 'inactive' | 'never' | 'ready';
export type DeviceContactMode = 'periodic' | 'on_demand';

export interface DeviceContactFreshness {
  activeMs: number;
  inactiveMs: number;
}

interface MaterialSystemConnectorLike {
  active: boolean;
  material_system_id: number | null;
  provider: string;
  transport: string;
  last_seen_at: string | null;
}

export type ConnectorChannel = 'edge' | 'orca' | 'moonraker' | 'octoprint' | 'adapter';
export type ObservationSource =
  | 'happyHareEdge'
  | 'happyHareMoonraker'
  | 'bambuLan'
  | 'orca'
  | 'octoprint'
  | 'manual'
  | 'adapter';

// The real touch source is the adapter's own request cadence (Moonraker's
// Spoolman polling, plugin sync), not a fixed heartbeat — thresholds are
// deliberately generous.
export const DEVICE_LINK_ACTIVE_MS = 120_000;
export const DEVICE_LINK_DELAYED_MS = 300_000;
const DEFAULT_CONTACT_FRESHNESS: DeviceContactFreshness = {
  activeMs: DEVICE_LINK_ACTIVE_MS,
  inactiveMs: DEVICE_LINK_DELAYED_MS,
};

/** Pick the freshest contact when both the printer and its connector report one. */
export function latestDeviceContact(
  ...timestamps: Array<string | null | undefined>
): string | null {
  let latest: string | null = null;
  let latestTime = Number.NEGATIVE_INFINITY;
  for (const timestamp of timestamps) {
    if (!timestamp) continue;
    const time = new Date(timestamp).getTime();
    if (Number.isFinite(time) && time > latestTime) {
      latest = timestamp;
      latestTime = time;
    }
  }
  return latest;
}

/** Active links that can report this material system, independent of array order. */
export function activeMaterialSystemConnectors<T extends MaterialSystemConnectorLike>(
  connectors: readonly T[],
  materialSystemId: number,
): T[] {
  return connectors.filter(
    (connector) => connector.active && connector.material_system_id === materialSystemId,
  );
}

/** Use the freshest system-specific link, retaining the printer fallback for legacy links. */
export function latestMaterialSystemContact(
  connectors: readonly MaterialSystemConnectorLike[],
  materialSystemId: number,
  printerLastSeenAt: string | null,
): string | null {
  const systemConnectors = activeMaterialSystemConnectors(connectors, materialSystemId);
  if (systemConnectors.length === 0) return latestDeviceContact(printerLastSeenAt);
  return latestDeviceContact(...systemConnectors.map((connector) => connector.last_seen_at));
}

export function connectorChannel(connector: Pick<MaterialSystemConnectorLike, 'provider' | 'transport'>): ConnectorChannel {
  const value = `${connector.provider} ${connector.transport}`.toLowerCase();
  if (value.includes('edge')) return 'edge';
  if (value.includes('orca')) return 'orca';
  if (value.includes('moonraker') || value.includes('klipper')) return 'moonraker';
  if (value.includes('octoprint')) return 'octoprint';
  return 'adapter';
}

/** Stable, deduplicated channel list. Multiple channels are not themselves a conflict. */
export function connectorChannels(
  connectors: readonly Pick<MaterialSystemConnectorLike, 'provider' | 'transport'>[],
): ConnectorChannel[] {
  const order: ConnectorChannel[] = ['edge', 'orca', 'moonraker', 'octoprint', 'adapter'];
  const channels = new Set(connectors.map(connectorChannel));
  return order.filter((channel) => channels.has(channel));
}

/** Translate normalized observation provenance without leaking internal source identifiers. */
export function observationSource(source: string | null | undefined): ObservationSource {
  const value = source?.toLowerCase() ?? '';
  if (value.includes('happy_hare') || value.includes('happy-hare') || value.startsWith('hh_')) {
    if (value.includes('edge')) return 'happyHareEdge';
    if (value.includes('moonraker') || value === 'hh_snapshot') return 'happyHareMoonraker';
  }
  if (value === 'bambu_lan_mqtt') return 'bambuLan';
  if (value.includes('orca')) return 'orca';
  if (value.includes('octoprint')) return 'octoprint';
  if (value === 'manual' || value === 'web_manual') return 'manual';
  return 'adapter';
}

export function formatLocalizedList(values: readonly string[], locale: string): string {
  return new Intl.ListFormat(locale, { style: 'long', type: 'conjunction' }).format(values);
}

interface StatusConnectorLike {
  active: boolean;
  last_seen_at: string | null;
  status_observation?: { received_at: string } | null;
}

/** Select only a genuinely fresh status, preferring the latest live connector. */
export function latestFreshStatusConnector<T extends StatusConnectorLike>(
  connectors: readonly T[],
  now: number = Date.now(),
): T | null {
  return connectors
    .filter(
      (connector) =>
        connector.active
        && connector.status_observation != null
        && getDeviceLinkState(connector.status_observation.received_at, now) === 'active',
    )
    .sort(
      (left, right) =>
        Date.parse(right.status_observation?.received_at ?? '')
        - Date.parse(left.status_observation?.received_at ?? ''),
    )[0] ?? null;
}

export function getDeviceLinkState(
  lastSeenAt: string | null,
  now: number = Date.now(),
  contactMode: DeviceContactMode = 'periodic',
  freshness: DeviceContactFreshness = DEFAULT_CONTACT_FRESHNESS,
): DeviceLinkState {
  if (!lastSeenAt) return 'never';
  // Some providers contact FH only when their local UI requests the spool list
  // or when a print reports usage. Silence between those actions is expected,
  // not delayed data.
  if (contactMode === 'on_demand') return 'ready';
  const diff = now - new Date(lastSeenAt).getTime();
  if (diff < freshness.activeMs) return 'active';
  if (diff < freshness.inactiveMs) return 'delayed';
  return 'inactive';
}

export function formatLastSeen(
  ts: string | null,
  t: (key: string, options?: Record<string, unknown>) => string,
  locale: string,
  now: number = Date.now(),
): string {
  if (!ts) return t('deviceLink.never');
  const d = new Date(ts);
  const diff = now - d.getTime();
  if (diff < 60_000) return t('deviceLink.time.ltMinute');
  if (diff < 3_600_000) return t('deviceLink.time.minutesAgo', { count: Math.floor(diff / 60_000) });
  if (diff < 86_400_000) return t('deviceLink.time.hoursAgo', { count: Math.floor(diff / 3_600_000) });
  return d.toLocaleDateString(locale);
}

/** Re-render tick so freshness badges don't freeze at mount time. */
export function useNow(intervalMs: number = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}
