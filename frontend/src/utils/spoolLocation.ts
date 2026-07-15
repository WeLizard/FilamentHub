// Spool location fields live in UserSpool.extra as JSON-encoded strings
// (Spoolman/Happy Hare convention): printer_name/mmu_gate_map hold the
// current slot, fhub_last_* remember the last released slot so identical
// spools of one catalog SKU stay tellable apart.

export interface SpoolSlotRef {
  printer: string;
  gate: number;
}

export interface SpoolLastLocation extends SpoolSlotRef {
  unloadedAt: string | null;
}

function parseJsonString(raw: string | undefined): string {
  if (!raw) return '';
  try {
    const value = JSON.parse(raw);
    return typeof value === 'string' ? value : '';
  } catch {
    return raw;
  }
}

function parseJsonGate(raw: string | undefined): number {
  if (raw == null || raw === '') return -1;
  try {
    const value = JSON.parse(raw);
    const gate = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(gate) ? gate : -1;
  } catch {
    return -1;
  }
}

export function getSpoolCurrentLocation(
  extra: Record<string, string> | null | undefined,
): SpoolSlotRef | null {
  if (!extra) return null;
  const printer = parseJsonString(extra.printer_name);
  const gate = parseJsonGate(extra.mmu_gate_map);
  if (!printer || gate < 0) return null;
  return { printer, gate };
}

export function getSpoolLastLocation(
  extra: Record<string, string> | null | undefined,
): SpoolLastLocation | null {
  if (!extra) return null;
  const printer = parseJsonString(extra.fhub_last_printer);
  const gate = parseJsonGate(extra.fhub_last_gate);
  if (!printer || gate < 0) return null;
  const unloadedAt = parseJsonString(extra.fhub_last_unloaded_at) || null;
  return { printer, gate, unloadedAt };
}
