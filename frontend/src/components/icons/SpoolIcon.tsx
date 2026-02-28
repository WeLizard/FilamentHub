import { useId } from 'react';

interface SpoolIconProps {
  /** Remaining filament 0–100 % */
  pct: number;
  /** Filament color as CSS hex, e.g. "#ff6b35" or "ff6b35" */
  color?: string;
  /** Remaining weight label source (grams) */
  remainingWeightG?: number | null;
  /** Show compact metric badges on icon */
  showMetrics?: boolean;
  size?: number;
  className?: string;
  viewBox?: string;
}

/**
 * SVG spool icon — 3/4 perspective view.
 * Colored filament ring shrinks toward the hub as pct decreases.
 */
export const SpoolIcon: React.FC<SpoolIconProps> = ({
  pct,
  color = '#9333ea',
  remainingWeightG = null,
  showMetrics = false,
  size = 80,
  className,
  viewBox = '0 0 100 100',
}) => {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');
  const fill = Math.max(0, Math.min(100, pct)) / 100;

  const c = color.startsWith('#') ? color : `#${color}`;

  // --- Geometry: nearly-circular flanges, 3D via offset only ---
  // Front flange
  const fx = 40;
  const fy = 52;
  const fRx = 30;
  const fRy = 31;

  // Back flange (offset gives depth)
  const bx = 55;
  const by = 44;

  // Hub (center hole)
  const hRx = 7.5;
  const hRy = 7.5;

  // Filament ring: interpolate between hub and max radius
  const maxRx = 24;
  const maxRy = 25;
  const filRx = hRx + (maxRx - hRx) * fill;
  const filRy = hRy + (maxRy - hRy) * fill;

  // Unique gradient IDs
  const faceId = `sf-${uid}`;
  const filFrontId = `sff-${uid}`;
  const filBackId = `sfb-${uid}`;

  const clampedPct = Math.round(fill * 100);
  const weightLabel =
    remainingWeightG == null ? null : `${Math.max(0, Math.round(remainingWeightG))}g`;

  return (
    <svg
      viewBox={viewBox}
      width={size}
      height={size}
      className={className}
      aria-label={`Spool ${Math.round(pct)}%`}
    >
      <defs>
        <radialGradient id={faceId} cx="40%" cy="32%" r="65%">
          <stop offset="0%" stopColor="#383854" />
          <stop offset="100%" stopColor="#1c1c2e" />
        </radialGradient>
        <radialGradient id={filFrontId} cx="36%" cy="28%" r="72%">
          <stop offset="0%" stopColor={c} stopOpacity="1" />
          <stop offset="80%" stopColor={c} stopOpacity="0.88" />
          <stop offset="100%" stopColor={c} stopOpacity="0.55" />
        </radialGradient>
        <radialGradient id={filBackId} cx="36%" cy="28%" r="72%">
          <stop offset="0%" stopColor={c} stopOpacity="1" />
          <stop offset="80%" stopColor={c} stopOpacity="0.88" />
          <stop offset="100%" stopColor={c} stopOpacity="0.55" />
        </radialGradient>
      </defs>

      {/* === Back flange === */}
      <ellipse
        cx={bx}
        cy={by}
        rx={fRx}
        ry={fRy}
        fill="#191928"
        stroke="#353550"
        strokeWidth="1.1"
      />
      {/* Back filament disc (visible behind front, creates depth illusion) */}
      {fill > 0.01 && (
        <ellipse
          cx={bx}
          cy={by}
          rx={filRx}
          ry={filRy}
          fill={`url(#${filBackId})`}
        />
      )}
      {/* Back hub hole */}
      <ellipse cx={bx} cy={by} rx={6.5} ry={6.5} fill="#0e0e1b" />

      {/* === Front flange face === */}
      <ellipse
        cx={fx}
        cy={fy}
        rx={fRx}
        ry={fRy}
        fill={`url(#${faceId})`}
      />

      {/* === Front filament ring === */}
      {fill > 0.01 && (
        <>
          <ellipse
            cx={fx}
            cy={fy}
            rx={filRx}
            ry={filRy}
            fill={`url(#${filFrontId})`}
          />
          <ellipse
            cx={fx}
            cy={fy}
            rx={filRx}
            ry={filRy}
            fill="none"
            stroke={c}
            strokeOpacity={0.22 + fill * 0.4}
            strokeWidth="0.65"
          />
        </>
      )}

      {/* === Front hub === */}
      <ellipse cx={fx} cy={fy} rx={hRx} ry={hRy} fill="#0e0e1b" />
      <ellipse cx={fx} cy={fy} rx={3.3} ry={3.3} fill="#07070d" />
      <ellipse
        cx={fx}
        cy={fy}
        rx={hRx}
        ry={hRy}
        fill="none"
        stroke="#28283e"
        strokeWidth="0.58"
      />

      {/* === Front flange rim === */}
      <ellipse
        cx={fx}
        cy={fy}
        rx={fRx}
        ry={fRy}
        fill="none"
        stroke="#3d3d5e"
        strokeWidth="1.8"
      />
      {/* Inner ring detail */}
      <ellipse
        cx={fx}
        cy={fy}
        rx={fRx - 2.5}
        ry={fRy - 2.5}
        fill="none"
        stroke="#2b2b45"
        strokeWidth="0.5"
        opacity="0.5"
      />

      {/* === Highlight === */}
      <ellipse
        cx={fx - 5.5}
        cy={fy - 12}
        rx={7}
        ry={2.5}
        fill="white"
        opacity="0.06"
        transform={`rotate(-10, ${fx - 5.5}, ${fy - 12})`}
      />

      {/* === Metric badges === */}
      {showMetrics && (
        <g>
          {weightLabel && (
            <>
              <rect
                x="7"
                y="69"
                width="36"
                height="14"
                rx="4"
                fill="rgba(8,8,14,0.85)"
                stroke="#3b3b58"
                strokeWidth="0.6"
              />
              <text
                x="25"
                y="78.2"
                textAnchor="middle"
                fill="#e5e7eb"
                fontSize="8.4"
                fontWeight="700"
                fontFamily="system-ui, sans-serif"
              >
                {weightLabel}
              </text>
            </>
          )}

          <rect
            x="47"
            y="69"
            width="24"
            height="14"
            rx="4"
            fill="rgba(8,8,14,0.85)"
            stroke="#3b3b58"
            strokeWidth="0.6"
          />
          <text
            x="59"
            y="78.2"
            textAnchor="middle"
            fill="#d8b4fe"
            fontSize="8.2"
            fontWeight="700"
            fontFamily="system-ui, sans-serif"
          >
            {clampedPct}%
          </text>
        </g>
      )}
    </svg>
  );
};
