import type { Preset } from '../types/api';

export const colorVariantsQueryKey = (filamentId: number | null | undefined) =>
  ['filament-color-variants', filamentId] as const;

/** How a colour of a material is called: its name, else its HEX, else the material. */
export const colorLabel = (filament: {
  name: string;
  color_name?: string | null;
  color_hex?: string | null;
}): string => filament.color_name || filament.color_hex?.toUpperCase() || filament.name;

const escapeForPattern = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * The preset name with the new colour in place of the old one, as the server
 * names a copy. A name that does not mention the old colour stays as written.
 */
export const nameForColor = (
  name: string,
  from: { color_name?: string | null },
  to: { name: string; color_name?: string | null; color_hex?: string | null },
): string => {
  const oldColour = from.color_name?.trim();
  const newColour = colorLabel(to).trim();
  if (!oldColour || !newColour) return name;
  const wholeWord = new RegExp(
    `(?<![\\p{L}\\p{N}_])${escapeForPattern(oldColour)}(?![\\p{L}\\p{N}_])`,
    'giu',
  );
  return name.replace(wholeWord, () => newColour);
};

/**
 * A private draft made on the site from another preset for another colour.
 *
 * Profile lists replace `source` with their own 'own' / 'saved' marks, so a
 * copy is also recognised by its provenance: it points at a source preset and,
 * unlike a slicer fork, has no slicer identity of its own.
 */
export const isColorCopyDraft = (
  preset: Pick<Preset, 'active' | 'source' | 'derived_from_preset_id' | 'external_id'> | null | undefined,
): boolean =>
  !!preset
  && !preset.active
  && (preset.source === 'copy' || (preset.derived_from_preset_id != null && !preset.external_id));

/** Whether this person may make a copy: of their own preset or of a published one. */
export const canCopyForColor = (
  preset: Pick<Preset, 'id' | 'active' | 'filament_id' | 'user_id'> | null | undefined,
  userId: number | null | undefined,
): boolean =>
  !!preset?.id && !!preset.filament_id && !!userId && (preset.active || preset.user_id === userId);
