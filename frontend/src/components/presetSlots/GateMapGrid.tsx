import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import type { GateState, MaterialSlot, UserSpool } from '../../api/client';
import type { Preset } from '../../types/api';
import { compareMaterialSlot } from '../../utils/materialSlotComparison';
import { NozzleRequirementBadge } from '../NozzleRequirementBadge';

interface GateMapGridProps {
  slots: MaterialSlot[];
  gates: GateState[];
  presets: Record<number, Pick<Preset, 'id' | 'name' | 'extruder_temp' | 'bed_temp'>>;
  spools: UserSpool[];
  providerLabel: string;
  nozzleHrc?: number | null;
  onGateClick: (gate: GateState | null, slot: MaterialSlot) => void;
}

function SpoolIcon({
  color,
  remainingPct,
  isEmpty,
  isUnknown,
  size = 56,
}: {
  color?: string | null;
  remainingPct?: number | null;
  isEmpty?: boolean;
  isUnknown?: boolean;
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
      {isUnknown && (
        <text
          x={center}
          y={center + 1}
          dominantBaseline="middle"
          textAnchor="middle"
          fill="rgb(253 230 138)"
          fontSize={size * 0.32}
          fontWeight="700"
        >
          ?
        </text>
      )}
    </svg>
  );
}

function observationLabel(
  state: ReturnType<typeof compareMaterialSlot>['observationState'],
  material: string | null,
  t: (key: string) => string,
): string {
  if (state === 'empty') return t('presetSlots.hhStatus.empty');
  if (state === 'buffer') {
    return material
      ? `${material} · ${t('presetSlots.hhStatus.buffer')}`
      : t('presetSlots.hhStatus.buffer');
  }
  if (state === 'loaded') return material ?? t('presetSlots.hhStatus.spool');
  if (state === 'unknown') return t('presetSlots.hhStatus.unknown');
  return t('presetSlots.observation.noData');
}

export function GateMapGrid({
  slots,
  gates,
  presets,
  spools,
  providerLabel,
  nozzleHrc = null,
  onGateClick,
}: GateMapGridProps) {
  const { t } = useTranslation();

  const gateMap = new Map<number, GateState>(gates.map((g) => [g.gate_index, g]));
  const spoolMap = new Map<number, UserSpool>(spools.map((s) => [s.id, s]));

  const sortedSlots = [...slots].sort(
    (left, right) => left.provider_index - right.provider_index || left.id - right.id,
  );

  return (
    <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4 xl:grid-cols-8">
      {sortedSlots.map((slot) => {
        const gate = gateMap.get(slot.provider_index) ?? null;
        const desiredSpoolId = slot.assignment?.spool_id ?? gate?.spool_id ?? null;
        const spool = desiredSpoolId != null ? spoolMap.get(desiredSpoolId) ?? null : null;
        const comparison = compareMaterialSlot(slot, gate, spool);
        const preset = comparison.desiredPresetId != null
          ? presets[comparison.desiredPresetId]
          : null;

        const spoolColor = spool?.filament?.color_hex
          ? `#${spool.filament.color_hex.replace(/^#/, '')}`
          : null;
        const observedColor = comparison.observedColorHex
          ? `#${comparison.observedColorHex}`
          : null;
        const displayMaterial = spool?.filament?.material_type ?? null;
        const hasDesired = comparison.desiredPresetId != null || comparison.desiredSpoolId != null;
        const hasObservation = comparison.observationState !== 'none';
        const hasConflict = comparison.conflict != null;
        const conflictKey = comparison.conflict
          ? `presetSlots.observation.conflict.${comparison.conflict}`
          : null;
        const actionKey = comparison.conflict
          ? `presetSlots.observation.action.${comparison.conflict}`
          : null;

        return (
          <div
            key={slot.id}
            className={[
              'group relative flex min-w-0 flex-col rounded-xl border text-center transition',
              'hover:border-purple-500/50 hover:bg-purple-500/8 focus:outline-none focus:ring-2 focus:ring-purple-500/40',
              hasConflict
                ? 'border-amber-400/40 bg-amber-500/[0.06]'
                : hasDesired
                ? 'border-purple-500/25 bg-purple-500/[0.04]'
                : 'border-white/[0.06] bg-white/[0.015]',
            ].join(' ')}
          >
            <button
              type="button"
              onClick={() => onGateClick(gate, slot)}
              title={slot.label ?? undefined}
              className="flex min-w-0 flex-1 flex-col items-center gap-1 px-2 pb-1.5 pt-2 focus:outline-none"
            >
              <div className="flex w-full items-center justify-between">
                <span
                  className={[
                    'flex h-5 min-w-[20px] items-center justify-center rounded-md px-1.5 text-[11px] font-bold',
                    hasDesired ? 'bg-purple-500/20 text-purple-300' : 'bg-white/8 text-gray-400',
                  ].join(' ')}
                >
                  {slot.provider_index}
                </span>
                <span className="text-[9px] font-medium uppercase tracking-wide text-gray-500">
                  {t('presetSlots.assignment.label')}
                </span>
              </div>

              <div className="py-0.5">
                <SpoolIcon
                  color={spoolColor}
                  remainingPct={spool?.remaining_pct}
                  isEmpty={!spool}
                />
              </div>

              {displayMaterial ? (
                <span className="text-xs font-medium text-gray-200">{displayMaterial}</span>
              ) : (
                <span className="text-[11px] text-gray-400">
                  {t('presetSlots.assignment.notAssigned')}
                </span>
              )}

              {spool?.filament && (
                <p className="max-w-full truncate text-[10px] leading-tight text-gray-300">
                  {[spool.filament.brand_name, spool.filament.name].filter(Boolean).join(' ')}
                </p>
              )}

              <NozzleRequirementBadge
                requiredHrc={spool?.filament?.required_nozzle_hrc}
                configuredHrc={nozzleHrc}
                size="tight"
                compact
              />

              {spool && (
                <span className="text-[10px] tabular-nums text-gray-300">
                  {spool.remaining_weight_g.toFixed(0)}g &middot; {spool.remaining_pct.toFixed(0)}%
                </span>
              )}

              {preset && (
                <div className="w-full min-w-0 border-t border-white/5 pt-1">
                  <p className="truncate text-[10px] font-medium text-purple-300">{preset.name}</p>
                  <p className="text-[9px] tabular-nums text-gray-400">
                    {preset.extruder_temp}&deg;C / {preset.bed_temp}&deg;C
                  </p>
                </div>
              )}
            </button>

            <button
              type="button"
              onClick={() => onGateClick(gate, slot)}
              title={conflictKey ? t(conflictKey) : undefined}
              className={[
                'mx-1.5 mb-1.5 flex min-w-0 items-center gap-1.5 rounded-lg border px-2 py-1.5 text-left transition',
                hasConflict
                  ? 'border-amber-400/20 bg-amber-500/10 hover:bg-amber-500/15'
                  : hasObservation
                    ? 'border-emerald-400/10 bg-emerald-500/[0.06] hover:bg-emerald-500/10'
                    : 'border-white/[0.05] bg-black/10 hover:bg-white/[0.04]',
              ].join(' ')}
            >
              {hasConflict ? (
                <AlertTriangle className="h-3 w-3 shrink-0 text-amber-300" />
              ) : hasObservation ? (
                <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald-400/80" />
              ) : (
                <span className="h-2 w-2 shrink-0 rounded-full bg-gray-600" />
              )}
              {observedColor && comparison.observationState !== 'empty' && (
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full border border-white/20"
                  style={{ backgroundColor: observedColor }}
                />
              )}
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[8px] uppercase tracking-wide text-gray-500">
                  {providerLabel}
                </span>
                <span className={[
                  'block truncate text-[9px]',
                  hasConflict ? 'text-amber-200' : 'text-gray-300',
                ].join(' ')}>
                  {observationLabel(
                    comparison.observationState,
                    comparison.observedMaterial,
                    t,
                  )}
                </span>
              </span>
              {actionKey && (
                <span className="shrink-0 text-[9px] font-medium text-amber-200 underline decoration-amber-300/40 underline-offset-2">
                  {t(actionKey)}
                </span>
              )}
            </button>
          </div>
        );
      })}
    </div>
  );
}
