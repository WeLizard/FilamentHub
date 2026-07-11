/** Color provenance helpers for parsed G-code and assigned catalog materials. */

export const normalizeFilamentColor = (value: string | null | undefined): string | null => {
  if (!value) return null;
  const normalized = value.trim().startsWith('#') ? value.trim() : `#${value.trim()}`;
  if (/^#[0-9a-f]{8}$/i.test(normalized)) return normalized.slice(0, 7).toUpperCase();
  return /^#[0-9a-f]{6}$/i.test(normalized) ? normalized.toUpperCase() : null;
};

export interface MaterialDisplayColors {
  primary: string | null;
  assigned: string | null;
  differs: boolean;
}

export const resolveMaterialDisplayColors = (
  parsedColor: string | null | undefined,
  assignedColor: string | null | undefined,
): MaterialDisplayColors => {
  const parsed = normalizeFilamentColor(parsedColor);
  const assigned = normalizeFilamentColor(assignedColor);
  const differs = Boolean(parsed && assigned && parsed !== assigned);
  return {
    primary: parsed || assigned,
    assigned: differs ? assigned : null,
    differs,
  };
};
