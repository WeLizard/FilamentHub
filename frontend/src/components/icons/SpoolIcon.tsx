import { useId } from 'react';

interface SpoolIconProps {
  /** Remaining filament 0–100 % */
  pct: number;
  /** Filament color as CSS hex, e.g. "#ff6b35" or "ff6b35" */
  color?: string;
  size?: number;
  className?: string;
}

/**
 * SVG spool icon in 3/4 perspective view.
 * The filament fill is a solid mass that shrinks from the outer edge
 * toward the hub as `pct` decreases.
 */
export const SpoolIcon: React.FC<SpoolIconProps> = ({
  pct,
  color = '#9333ea',
  size = 80,
  className,
}) => {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');
  const fill = Math.max(0, Math.min(100, pct)) / 100;

  // Normalise color to always have a leading #
  const c = color.startsWith('#') ? color : `#${color}`;

  // ── Front flange geometry ─────────────────────────────────
  const fx = 44, fy = 52;
  const fRx = 36, fRy = 41;

  // ── Back flange (3/4 depth offset: right + up) ────────────
  const bx = fx + 13, by = fy - 7; // (57, 45)

  // ── Hub (axle area on front face) ─────────────────────────
  const hRx = 9, hRy = 10;

  // ── Filament fill: interpolates from hub size to max fill ─
  const maxRx = 31, maxRy = 36;
  const filRx = hRx + (maxRx - hRx) * fill;
  const filRy = hRy + (maxRy - hRy) * fill;

  // Gradient IDs (unique per instance to avoid SVG ID collisions)
  const faceId = `sf${uid}`;
  const filId  = `sf${uid}f`;

  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      className={className}
      aria-label={`Spool ${Math.round(pct)}%`}
    >
      <defs>
        {/* Front face radial gradient */}
        <radialGradient id={faceId} cx="40%" cy="32%" r="65%">
          <stop offset="0%"   stopColor="#383854" />
          <stop offset="100%" stopColor="#1c1c2e" />
        </radialGradient>

        {/* Filament radial gradient (lighter center, darker edge) */}
        <radialGradient id={filId} cx="36%" cy="28%" r="72%">
          <stop offset="0%"   stopColor={c} stopOpacity="1"    />
          <stop offset="80%"  stopColor={c} stopOpacity="0.88" />
          <stop offset="100%" stopColor={c} stopOpacity="0.55" />
        </radialGradient>
      </defs>

      {/* ── 1. Back flange ────────────────────────────────────── */}
      <ellipse
        cx={bx} cy={by} rx={fRx} ry={fRy}
        fill="#191928" stroke="#353550" strokeWidth="1.5"
      />
      {/* Back hub */}
      <ellipse cx={bx} cy={by} rx={hRx - 1} ry={hRy - 1} fill="#0e0e1b" />

      {/* ── 2. Barrel top strip (visible top of cylinder) ────── */}
      {/* Parallelogram connecting front-top to back-top */}
      <path
        d={`M ${fx} ${fy - fRy} L ${bx} ${by - fRy}
            L ${bx + 2} ${by - fRy + 6} L ${fx + 1} ${fy - fRy + 6} Z`}
        fill="#222236"
      />
      <line
        x1={fx} y1={fy - fRy}
        x2={bx} y2={by - fRy}
        stroke="#353550" strokeWidth="1"
      />

      {/* ── 3. Front flange face ─────────────────────────────── */}
      <ellipse cx={fx} cy={fy} rx={fRx} ry={fRy} fill={`url(#${faceId})`} />

      {/* ── 4. Filament fill (solid mass, shrinks toward hub) ── */}
      {fill > 0 && (
        <ellipse
          cx={fx} cy={fy}
          rx={filRx} ry={filRy}
          fill={`url(#${filId})`}
          style={{
            // SVG2 CSS geometry properties for transitions (Chrome 77+, Firefox 72+, Safari 14.1+)
            transition: 'rx 0.45s ease-out, ry 0.45s ease-out',
          } as React.CSSProperties & { rx?: number; ry?: number }}
        />
      )}

      {/* ── 5. Hub over filament ──────────────────────────────── */}
      <ellipse cx={fx} cy={fy} rx={hRx}   ry={hRy}   fill="#0e0e1b" />
      <ellipse cx={fx} cy={fy} rx={4}     ry={4.5}   fill="#07070d" />
      <ellipse cx={fx} cy={fy} rx={hRx}   ry={hRy}   fill="none" stroke="#28283e" strokeWidth="0.8" />

      {/* ── 6. Front flange rim ───────────────────────────────── */}
      <ellipse
        cx={fx} cy={fy} rx={fRx} ry={fRy}
        fill="none" stroke="#3d3d5e" strokeWidth="2.5"
      />
      {/* Inner groove detail */}
      <ellipse
        cx={fx} cy={fy}
        rx={Math.round(fRx * 0.9)} ry={Math.round(fRy * 0.9)}
        fill="none" stroke="#2b2b45" strokeWidth="0.7" opacity="0.5"
      />

      {/* ── 7. Subtle top highlight ───────────────────────────── */}
      <ellipse
        cx={fx - 7} cy={fy - 17}
        rx={9} ry={3.5}
        fill="white" opacity="0.06"
        transform={`rotate(-12, ${fx - 7}, ${fy - 17})`}
      />
    </svg>
  );
};
