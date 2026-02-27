import { useTranslation } from 'react-i18next';
import type { GateState, UserPrinterDevice, UserSpool } from '../../api/client';
import type { Preset } from '../../types/api';

interface GateMapGridProps {
  device: UserPrinterDevice;
  gates: GateState[];
  /** Cached preset data by id */
  presets: Record<number, Pick<Preset, 'id' | 'name' | 'extruder_temp' | 'bed_temp'>>;
  /** User's spools for spool-to-gate display */
  spools: UserSpool[];
  onGateClick: (gate: GateState | null, gateIndex: number) => void;
}

function hhStatusLabel(status: number | null, t: (k: string) => string): string {
  if (status === null || status === -1) return t('presetSlots.hhStatus.unknown');
  if (status === 0) return t('presetSlots.hhStatus.empty');
  if (status === 1) return t('presetSlots.hhStatus.spool');
  if (status === 2) return t('presetSlots.hhStatus.buffer');
  return '';
}

function sourceLabel(source: GateState['source'], t: (k: string) => string): string {
  return t(`presetSlots.source.${source}`);
}

export function GateMapGrid({ device, gates, presets, spools, onGateClick }: GateMapGridProps) {
  const { t } = useTranslation();

  const gateMap = new Map<number, GateState>(gates.map((g) => [g.gate_index, g]));
  const spoolMap = new Map<number, UserSpool>(spools.map((s) => [s.id, s]));

  const totalGates = device.gate_count ?? Math.max(gates.length, 4);

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {Array.from({ length: totalGates }, (_, i) => {
        const gate = gateMap.get(i) ?? null;
        const preset = gate?.preset_id != null ? presets[gate.preset_id] : null;
        const spool = gate?.spool_id != null ? spoolMap.get(gate.spool_id) : null;

        // Color priority: spool filament color → HH color
        const spoolColor = spool?.filament?.color_hex
          ? `#${spool.filament.color_hex.replace(/^#/, '')}`
          : null;
        const hhColor = gate?.hh_color_hex ? `#${gate.hh_color_hex.replace(/^#/, '')}` : null;
        const displayColor = spoolColor ?? hhColor;

        // Material: spool filament material → HH material
        const displayMaterial =
          spool?.filament?.material_type ?? gate?.hh_material ?? null;

        const hasAssignment = !!(gate?.preset_id || gate?.spool_id);

        return (
          <button
            key={i}
            type="button"
            onClick={() => onGateClick(gate, i)}
            className={[
              'group relative flex flex-col gap-1.5 rounded-xl border p-3 text-left transition',
              'hover:border-purple-500/60 hover:bg-purple-500/10 focus:outline-none focus:ring-2 focus:ring-purple-500/50',
              hasAssignment
                ? 'border-purple-500/40 bg-purple-500/10'
                : 'border-white/10 bg-white/[0.02]',
            ].join(' ')}
          >
            {/* Gate number + source */}
            <div className="flex items-center justify-between gap-1">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/10 text-xs font-bold text-white">
                {i}
              </span>
              {gate && (
                <span className="rounded px-1 py-0.5 text-[10px] text-gray-500">
                  {sourceLabel(gate.source, t)}
                </span>
              )}
            </div>

            {/* Color swatch + material */}
            {(displayColor || displayMaterial) && (
              <div className="flex items-center gap-1.5">
                {displayColor && (
                  <span
                    className="h-3.5 w-3.5 flex-shrink-0 rounded-full border border-white/20 shadow"
                    style={{ backgroundColor: displayColor }}
                  />
                )}
                {displayMaterial && (
                  <span className="truncate text-xs text-gray-300">{displayMaterial}</span>
                )}
                {gate?.hh_status != null && gate.hh_status !== 1 && (
                  <span className="text-xs text-gray-500">
                    · {hhStatusLabel(gate.hh_status, t)}
                  </span>
                )}
              </div>
            )}

            {/* Spool filament name */}
            {spool?.filament && (
              <p className="truncate text-[11px] text-gray-400">
                {[spool.filament.brand_name, spool.filament.name]
                  .filter(Boolean)
                  .join(' ')}
              </p>
            )}

            {/* Preset name */}
            {preset ? (
              <div className="min-w-0">
                <p className="truncate text-xs font-medium text-purple-300">{preset.name}</p>
                <p className="text-[10px] text-gray-500">
                  {preset.extruder_temp}°C / {preset.bed_temp}°C
                </p>
              </div>
            ) : (
              <p className="text-xs text-gray-600">{t('presetSlots.gateEmpty')}</p>
            )}

            {/* Hover hint overlay */}
            <span className="absolute inset-0 flex items-center justify-center rounded-xl bg-black/0 opacity-0 transition group-hover:opacity-100">
              <span className="rounded-lg bg-purple-600/85 px-2 py-1 text-xs font-medium text-white backdrop-blur-sm">
                {t('presetSlots.assignPreset')}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
