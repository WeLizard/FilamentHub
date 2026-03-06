import { useTranslation } from 'react-i18next';
import type { GateState, UserPrinterDevice, UserSpool } from '../../api/client';
import type { Preset } from '../../types/api';

interface GateMapGridProps {
  device: UserPrinterDevice;
  gates: GateState[];
  presets: Record<number, Pick<Preset, 'id' | 'name' | 'extruder_temp' | 'bed_temp'>>;
  spools: UserSpool[];
  onGateClick: (gate: GateState | null, gateIndex: number) => void;
}

function SpoolIcon({
  color,
  remainingPct,
  isEmpty,
  size = 56,
}: {
  color?: string | null;
  remainingPct?: number | null;
  isEmpty?: boolean;
  size?: number;
}) {
  const center = size / 2;
  const outerR = size / 2 - 2;
  const filamentR = size * 0.36;
  const innerR = size / 7;
  const circumference = 2 * Math.PI * filamentR;
  const pct = remainingPct != null ? Math.max(0, Math.min(100, remainingPct)) : 100;
  const dashOffset = circumference * (1 - pct / 100);
  const fillColor = color || 'rgba(168, 85, 247, 0.5)';

  if (isEmpty) {
    return (
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={center} cy={center} r={outerR} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="1" strokeDasharray="3 3" />
        <circle cx={center} cy={center} r={filamentR} fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="7" strokeDasharray="3 3" />
        <circle cx={center} cy={center} r={innerR} fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.07)" strokeWidth="0.75" />
      </svg>
    );
  }

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="drop-shadow">
      {/* Outer flange */}
      <circle cx={center} cy={center} r={outerR} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="1.5" />
      {/* Filament track background */}
      <circle cx={center} cy={center} r={filamentR} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="8" />
      {/* Filament remaining (colored arc) */}
      <circle
        cx={center} cy={center} r={filamentR}
        fill="none"
        stroke={fillColor}
        strokeWidth="8"
        strokeDasharray={circumference}
        strokeDashoffset={dashOffset}
        strokeLinecap="round"
        transform={`rotate(-90 ${center} ${center})`}
        opacity={0.9}
      />
      {/* Inner hub */}
      <circle cx={center} cy={center} r={innerR} fill="rgba(0,0,0,0.35)" stroke="rgba(255,255,255,0.1)" strokeWidth="0.75" />
      {/* Hub cross marks */}
      <line x1={center - innerR + 2} y1={center} x2={center + innerR - 2} y2={center} stroke="rgba(255,255,255,0.08)" strokeWidth="0.5" />
      <line x1={center} y1={center - innerR + 2} x2={center} y2={center + innerR - 2} stroke="rgba(255,255,255,0.08)" strokeWidth="0.5" />
    </svg>
  );
}

function hhStatusBadge(status: number | null, t: (k: string) => string): { label: string; cls: string } | null {
  if (status === null || status === -1 || status === 1) return null;
  if (status === 0) return { label: t('presetSlots.hhStatus.empty'), cls: 'bg-gray-700/50 text-gray-400' };
  if (status === 2) return { label: t('presetSlots.hhStatus.buffer'), cls: 'bg-amber-500/15 text-amber-400' };
  return null;
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

        const spoolColor = spool?.filament?.color_hex
          ? `#${spool.filament.color_hex.replace(/^#/, '')}`
          : null;
        const hhColor = gate?.hh_color_hex ? `#${gate.hh_color_hex.replace(/^#/, '')}` : null;
        const displayColor = spoolColor ?? hhColor;
        const displayMaterial = spool?.filament?.material_type ?? gate?.hh_material ?? null;
        const hasContent = !!(gate?.preset_id || gate?.spool_id || displayMaterial);
        const hhBadge = gate ? hhStatusBadge(gate.hh_status, t) : null;

        return (
          <button
            key={i}
            type="button"
            onClick={() => onGateClick(gate, i)}
            className={[
              'group relative flex flex-col items-center gap-1.5 rounded-xl border p-3 text-center transition',
              'hover:border-purple-500/50 hover:bg-purple-500/8 focus:outline-none focus:ring-2 focus:ring-purple-500/40',
              hasContent
                ? 'border-purple-500/25 bg-purple-500/[0.04]'
                : 'border-white/[0.06] bg-white/[0.015]',
            ].join(' ')}
          >
            {/* Header: gate number + source */}
            <div className="flex w-full items-center justify-between">
              <span
                className={[
                  'flex h-5 min-w-[20px] items-center justify-center rounded-md px-1.5 text-[11px] font-bold',
                  hasContent ? 'bg-purple-500/20 text-purple-300' : 'bg-white/5 text-gray-600',
                ].join(' ')}
              >
                {i}
              </span>
              {gate && (
                <span className="text-[9px] font-medium text-gray-600">
                  {gate.source === 'hh_snapshot' ? 'HH' : gate.source === 'manual_orca' ? 'Orca' : ''}
                </span>
              )}
            </div>

            {/* Spool icon */}
            <div className="py-1">
              <SpoolIcon
                color={displayColor}
                remainingPct={spool?.remaining_pct}
                isEmpty={!hasContent}
              />
            </div>

            {/* Material type */}
            {displayMaterial ? (
              <span className="text-xs font-medium text-gray-200">{displayMaterial}</span>
            ) : (
              <span className="text-[11px] text-gray-600">{t('presetSlots.gateEmpty')}</span>
            )}

            {/* Brand + filament name */}
            {spool?.filament && (
              <p className="max-w-full truncate text-[10px] leading-tight text-gray-400">
                {[spool.filament.brand_name, spool.filament.name].filter(Boolean).join(' ')}
              </p>
            )}

            {/* HH status badge (empty / buffer) */}
            {hhBadge && (
              <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-medium ${hhBadge.cls}`}>
                {hhBadge.label}
              </span>
            )}

            {/* Remaining weight */}
            {spool && (
              <span className="text-[10px] tabular-nums text-gray-500">
                {spool.remaining_weight_g}g &middot; {spool.remaining_pct}%
              </span>
            )}

            {/* Preset info */}
            {preset && (
              <div className="mt-0.5 w-full min-w-0 border-t border-white/5 pt-1.5">
                <p className="truncate text-[10px] font-medium text-purple-300">{preset.name}</p>
                <p className="text-[9px] tabular-nums text-gray-500">
                  {preset.extruder_temp}&deg;C / {preset.bed_temp}&deg;C
                </p>
              </div>
            )}

            {/* Hover overlay */}
            <span className="absolute inset-0 flex items-center justify-center rounded-xl opacity-0 transition group-hover:opacity-100">
              <span className="rounded-lg bg-purple-600/90 px-2.5 py-1 text-[10px] font-medium text-white shadow-lg backdrop-blur-sm">
                {t('presetSlots.assignPreset')}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
