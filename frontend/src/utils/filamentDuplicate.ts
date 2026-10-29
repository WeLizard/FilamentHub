import type { TFunction } from "i18next";

export interface FilamentSlugHolder {
  id: number;
  name: string;
  brandName?: string;
  materialType?: string;
  colorName?: string;
  colorHex?: string;
  inactive: boolean;
}

/** The catalog entry a rejected "create filament" request collided with. */
export function readFilamentSlugHolder(detail: unknown): FilamentSlugHolder | null {
  if (!detail || typeof detail !== "object") return null;
  const payload = detail as { code?: string; params?: Record<string, unknown> };
  if (payload.code !== "ERR_FILAMENT_ALREADY_EXISTS" || !payload.params) return null;
  const id = Number(payload.params.filament_id);
  if (!Number.isFinite(id) || id <= 0) return null;
  const text = (value: unknown) => (value ? String(value) : undefined);
  return {
    id,
    name: String(payload.params.filament_name ?? ""),
    brandName: text(payload.params.brand_name),
    materialType: text(payload.params.material_type),
    colorName: text(payload.params.color_name),
    colorHex: text(payload.params.color_hex),
    inactive: payload.params.inactive === true,
  };
}

export function filamentHolderLabel(holder: Pick<FilamentSlugHolder, "name" | "brandName" | "colorName">): string {
  const base = holder.brandName ? `${holder.brandName} ${holder.name}` : holder.name;
  return holder.colorName ? `${base} (${holder.colorName})` : base;
}

/** Message for a duplicate that cannot be picked from the list. */
export function filamentHolderMessage(t: TFunction, holder: FilamentSlugHolder): string {
  return t(
    holder.inactive
      ? "apiErrors.ERR_FILAMENT_ALREADY_EXISTS_INACTIVE"
      : "apiErrors.ERR_FILAMENT_ALREADY_EXISTS_NAMED",
    { name: filamentHolderLabel(holder) },
  );
}
