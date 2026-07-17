/**
 * Adapter-link freshness for user printer devices.
 *
 * `last_seen_at` records the last successful contact of the plugin/adapter
 * (Orca plugin, Happy Hare via the Spoolman-compatible API) with FilamentHub.
 * It says nothing about whether the physical printer is powered on — the UI
 * must present it as the state of the LINK, never as printer online/offline.
 */

import { useEffect, useState } from 'react';

export type DeviceLinkState = 'active' | 'delayed' | 'inactive' | 'never';

// The real touch source is the adapter's own request cadence (Moonraker's
// Spoolman polling, plugin sync), not a fixed heartbeat — thresholds are
// deliberately generous.
export const DEVICE_LINK_ACTIVE_MS = 60_000;
export const DEVICE_LINK_DELAYED_MS = 300_000;

export function getDeviceLinkState(lastSeenAt: string | null, now: number = Date.now()): DeviceLinkState {
  if (!lastSeenAt) return 'never';
  const diff = now - new Date(lastSeenAt).getTime();
  if (diff < DEVICE_LINK_ACTIVE_MS) return 'active';
  if (diff < DEVICE_LINK_DELAYED_MS) return 'delayed';
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
