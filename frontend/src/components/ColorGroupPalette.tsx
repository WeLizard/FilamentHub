import { useState } from 'react';
import type { FC } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { FilamentColorGroup, FilamentColorGroupSource } from '../types/api';
import {
  FILAMENT_COLOR_GROUP_PALETTE,
  FILAMENT_COLOR_GROUPS,
} from '../utils/filamentColorGroups';

interface ColorGroupPaletteProps {
  automaticGroup: FilamentColorGroup | null;
  selectedGroup: FilamentColorGroup | null;
  source: FilamentColorGroupSource;
  disabled?: boolean;
  onSelect: (group: FilamentColorGroup, colorHex: string) => void;
}

export const ColorGroupPalette: FC<ColorGroupPaletteProps> = ({
  automaticGroup,
  selectedGroup,
  source,
  disabled = false,
  onSelect,
}) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const visibleGroup = source === 'manual' ? selectedGroup : automaticGroup;
  const status = source === 'manual' && selectedGroup === null
    ? t('createFilament.detectedColorGroup', {
        group: t('createFilament.multicolorNoDominant'),
        mode: t('createFilament.colorGroupSource.manual'),
      })
    : visibleGroup
      ? t('createFilament.detectedColorGroup', {
          group: t(`colorGroups.${visibleGroup}`),
          mode: t(`createFilament.colorGroupSource.${source}`),
        })
      : t('createFilament.colorGroupNotDetected');

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.035]">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left transition-colors hover:bg-white/5"
        aria-expanded={expanded}
      >
        <span className="min-w-0">
          <span className="block text-xs font-medium text-gray-300">
            {t('createFilament.approximatePalette')}
          </span>
          <span className="block truncate text-xs text-gray-400">{status}</span>
        </span>
        {expanded
          ? <ChevronUp className="h-4 w-4 shrink-0 text-gray-400" />
          : <ChevronDown className="h-4 w-4 shrink-0 text-gray-400" />}
      </button>

      {expanded && (
        <div className="grid grid-cols-2 gap-2 border-t border-white/10 p-2 sm:grid-cols-3 lg:grid-cols-4">
          {FILAMENT_COLOR_GROUPS.map((group) => {
            const active = visibleGroup === group;
            return (
              <div
                key={group}
                className={`rounded-lg border p-2 transition-colors ${
                  active ? 'border-purple-400 bg-purple-500/15' : 'border-white/10 bg-black/10'
                }`}
              >
                <div className="mb-1.5 truncate text-[11px] font-medium text-gray-300">
                  {t(`colorGroups.${group}`)}
                </div>
                <div className="flex gap-1">
                  {FILAMENT_COLOR_GROUP_PALETTE[group].map((colorHex) => (
                    <button
                      key={colorHex}
                      type="button"
                      disabled={disabled}
                      onClick={() => onSelect(group, colorHex)}
                      className="h-5 min-w-0 flex-1 rounded border border-white/25 shadow-sm transition-transform hover:scale-110 focus:outline-none focus:ring-2 focus:ring-purple-400 disabled:cursor-not-allowed disabled:opacity-40"
                      style={{ backgroundColor: colorHex }}
                      aria-label={t('createFilament.selectApproximateShade', {
                        group: t(`colorGroups.${group}`),
                        hex: colorHex,
                      })}
                      title={colorHex}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
