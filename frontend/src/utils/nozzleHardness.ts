const NOZZLE_TYPE_HRC: Record<string, number> = {
  hardened_steel: 55,
  stainless_steel: 20,
  tungsten_carbide: 85,
  brass: 2,
  E3D: 55,
  undefine: 0,
};

function firstValue(raw: unknown): unknown {
  return Array.isArray(raw) ? raw[0] : raw;
}

export function configuredNozzleHrc(settings: Record<string, unknown> | null | undefined): number | null {
  if (!settings) {
    return null;
  }

  const explicit = Number(firstValue(settings.nozzle_hrc));
  if (Number.isFinite(explicit) && explicit > 0) {
    return explicit;
  }

  const type = firstValue(settings.nozzle_type);
  if (typeof type !== 'string') {
    return null;
  }

  const byType = NOZZLE_TYPE_HRC[type];
  return byType != null && byType > 0 ? byType : null;
}

export function isNozzleTooSoft(
  requiredHrc: number | null | undefined,
  configuredHrc: number | null | undefined,
): boolean {
  if (requiredHrc == null || configuredHrc == null) {
    return false;
  }
  return configuredHrc < requiredHrc;
}
