/**
 * Setting complexity levels mirrored from OrcaSlicer (`ConfigOptionDef.mode`), so the
 * Simple / Advanced / Expert selector matches what Orca users already know.
 * `simple` is shown to everyone; `advanced` and `expert` progressively reveal more.
 * The level of each field comes from the generated Orca preset schema.
 */

export type SettingMode = 'simple' | 'advanced' | 'expert';

export const SETTING_MODES: readonly SettingMode[] = ['simple', 'advanced', 'expert'];

export const MODE_RANK: Record<SettingMode, number> = { simple: 0, advanced: 1, expert: 2 };

/** True if a field of `fieldMode` (default 'simple') should show at `current`. */
export function isVisibleAtMode(fieldMode: SettingMode | undefined, current: SettingMode): boolean {
  return MODE_RANK[fieldMode ?? 'simple'] <= MODE_RANK[current];
}

