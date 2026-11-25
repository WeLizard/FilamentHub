import { useTranslation } from 'react-i18next';
import { ChevronRight } from 'lucide-react';
import type { EdgeBuild, EdgeNet, EdgePowerStage, EdgeWire } from './edgeBuilds';
import { DIAGRAM_GROUND, DIAGRAM_INK, DIAGRAM_MUTED, DIAGRAM_PART, DIAGRAM_POWER } from './edgeDiagram';

const PANEL = DIAGRAM_GROUND;
const ROW = 22;
const TOP = 34;
const BOARD_X = [40, 196];
const MODULE_X = [452, 640];
const LANE_X0 = 232;
const LANE_STEP = 17;
const POWER_COLORS: Partial<Record<EdgeNet, string>> = DIAGRAM_POWER;
const SIGNAL_COLORS = ['#4b9be6', '#3fbf92', '#3cc0d6', '#8087f2', '#dd7cc4', '#b088e0', '#7fd36b', '#e8c547', '#5fb3f0', '#f08bb0', '#9ad0c2'];
const POWER_PADS = ['5V', '3V3', 'GND'];

interface Lane {
  key: string;
  x: number;
  color: string;
  rows: number[];
  /** The board pad that feeds this lane, drawn on the board edge. */
  pad: string;
  padRow: number;
}

interface Layout {
  height: number;
  lanes: Lane[];
  blocks: { label: string; note?: string; top: number; rows: number }[];
  pins: { wire: EdgeWire; row: number; color: string; lane?: Lane }[];
  boardPads: { pad: string; row: number; color: string }[];
}

const rowY = (row: number) => TOP + row * ROW;

/** "ESP32-S3-DevKitC-1 N16R8" → ["ESP32-S3-DevKitC-1", "N16R8"]. */
const boardName = (name: string) => {
  const space = name.indexOf(' ');
  return space < 0 ? [name] : [name.slice(0, space), name.slice(space + 1)];
};

function layout(build: EdgeBuild): Layout {
  const colors = new Map<string, string>();
  const colorOf = (wire: EdgeWire) => {
    const power = POWER_COLORS[wire.net];
    if (power) return power;
    if (!colors.has(wire.boardPin)) colors.set(wire.boardPin, SIGNAL_COLORS[colors.size % SIGNAL_COLORS.length]);
    return colors.get(wire.boardPin)!;
  };

  // A board pad used by more than one module pin gets a vertical lane; power always does.
  const uses = new Map<string, number>();
  for (const wire of build.wires) uses.set(wire.boardPin, (uses.get(wire.boardPin) ?? 0) + 1);
  const shared = (pad: string) => POWER_PADS.includes(pad) || (uses.get(pad) ?? 0) > 1;

  const blocks: Layout['blocks'] = [];
  const pins: Layout['pins'] = [];
  let row = 4;
  for (const module of build.modules) {
    const own = build.wires.filter((wire) => wire.module === module.id);
    blocks.push({ label: module.label, note: module.note, top: row, rows: own.length + 1 + (module.note ? 1 : 0) });
    row += 1;
    for (const wire of own) pins.push({ wire, row: row++, color: colorOf(wire) });
    row += (module.note ? 1 : 0) + 1;
  }

  const lanes: Lane[] = [];
  const laneFor = (pad: string, color: string, firstRow: number) => {
    let lane = lanes.find((item) => item.key === pad);
    if (!lane) {
      const powerRow = POWER_PADS.indexOf(pad);
      lane = { key: pad, x: 0, color, rows: [], pad, padRow: powerRow >= 0 ? powerRow + 0.5 : firstRow };
      lanes.push(lane);
    }
    return lane;
  };
  for (const pin of pins) {
    if (!shared(pin.wire.boardPin)) continue;
    pin.lane = laneFor(pin.wire.boardPin, pin.color, pin.row);
    pin.lane.rows.push(pin.row);
  }
  // Power lanes sit next to the modules, signal buses next to the board.
  lanes.sort((a, b) => Number(POWER_PADS.includes(a.key)) - Number(POWER_PADS.includes(b.key)));
  lanes.forEach((lane, index) => { lane.x = LANE_X0 + index * LANE_STEP; });

  const boardPads: Layout['boardPads'] = [];
  for (const lane of lanes) boardPads.push({ pad: lane.pad, row: lane.padRow, color: lane.color });
  for (const pin of pins) if (!pin.lane) boardPads.push({ pad: pin.wire.boardPin, row: pin.row, color: pin.color });

  return { height: rowY(row) + 8, lanes, blocks, pins, boardPads };
}

export function EdgeBuildWiring({ build }: { build: EdgeBuild }) {
  const { t } = useTranslation();
  const { height, lanes, blocks, pins, boardPads } = layout(build);
  const boardBottom = rowY(Math.max(...boardPads.map((pad) => pad.row))) + 18;

  return (
    <figure>
      <div className="hidden rounded-2xl border border-white/10 p-3 md:block md:p-5" style={{ backgroundColor: PANEL }}>
        <svg viewBox={`20 0 640 ${height}`} role="img" aria-label={t('edgeBuilds.wiring.title')} className="h-auto w-full">
          {/* Lanes first: every wire drawn later crosses them, joins show as dots. */}
          {lanes.map((lane) => {
            const rows = [lane.padRow, ...lane.rows];
            return (
              <line
                key={lane.key}
                x1={lane.x}
                x2={lane.x}
                y1={rowY(Math.min(...rows))}
                y2={rowY(Math.max(...rows))}
                stroke={lane.color}
                strokeWidth={3}
                strokeLinecap="round"
              />
            );
          })}
          {lanes.map((lane) => (
            <g key={`feed-${lane.key}`}>
              <line x1={BOARD_X[1]} x2={lane.x} y1={rowY(lane.padRow)} y2={rowY(lane.padRow)} stroke={PANEL} strokeWidth={7} />
              <line x1={BOARD_X[1]} x2={lane.x} y1={rowY(lane.padRow)} y2={rowY(lane.padRow)} stroke={lane.color} strokeWidth={3} />
              <circle cx={lane.x} cy={rowY(lane.padRow)} r={4} fill={lane.color} />
            </g>
          ))}
          {pins.map(({ wire, row, color, lane }) => {
            const from = lane ? lane.x : BOARD_X[1];
            const y = rowY(row);
            return (
              <g key={`${wire.module}-${wire.modulePin}`}>
                <line x1={from} x2={MODULE_X[0]} y1={y} y2={y} stroke={PANEL} strokeWidth={7} />
                <line x1={from} x2={MODULE_X[0]} y1={y} y2={y} stroke={color} strokeWidth={3} strokeLinecap="round" />
                {lane && <circle cx={lane.x} cy={y} r={4} fill={color} />}
              </g>
            );
          })}

          <rect x={BOARD_X[0]} y={TOP - 18} width={BOARD_X[1] - BOARD_X[0]} height={boardBottom - TOP + 18} rx={9} fill={DIAGRAM_PART} stroke={DIAGRAM_INK} strokeWidth={1.25} />
          {/* Two lines keep a long board name inside the block. */}
          <text x={(BOARD_X[0] + BOARD_X[1]) / 2} y={rowY(3.2)} fontSize={10.5} fontWeight={700} textAnchor="middle" fill="#fff">
            {boardName(build.board).map((line, index) => (
              <tspan key={line} x={(BOARD_X[0] + BOARD_X[1]) / 2} dy={index === 0 ? 0 : 13}>{line}</tspan>
            ))}
          </text>
          {boardPads.map(({ pad, row, color }) => (
            <g key={`pad-${pad}`}>
              <circle cx={BOARD_X[1]} cy={rowY(row)} r={6} fill={color} stroke={PANEL} />
              <text x={BOARD_X[1] - 12} y={rowY(row) + 3.5} fontSize={10} fontWeight={700} textAnchor="end" fill={DIAGRAM_INK}>{pad}</text>
            </g>
          ))}

          {blocks.map((block) => (
            <g key={block.label}>
              <rect x={MODULE_X[0]} y={rowY(block.top) - 12} width={MODULE_X[1] - MODULE_X[0]} height={block.rows * ROW + 4} rx={8} fill={DIAGRAM_PART} stroke={DIAGRAM_INK} strokeWidth={1.25} />
              <text x={MODULE_X[0] + 14} y={rowY(block.top) + 4} fontSize={11} fontWeight={700} fill="#fff">{block.label}</text>
              {block.note && (
                <text x={MODULE_X[0] + 14} y={rowY(block.top + block.rows - 1) + 4} fontSize={9.5} fill={DIAGRAM_MUTED}>{t(block.note)}</text>
              )}
            </g>
          ))}
          {pins.map(({ wire, row, color }) => (
            <g key={`label-${wire.module}-${wire.modulePin}`}>
              <circle cx={MODULE_X[0]} cy={rowY(row)} r={6} fill={color} stroke={PANEL} />
              <text x={MODULE_X[0] + 14} y={rowY(row) + 3.5} fontSize={10} fontWeight={600} fill={DIAGRAM_INK}>{wire.modulePin}</text>
            </g>
          ))}
        </svg>
      </div>

      <WireTable build={build} colors={new Map(pins.map(({ wire, color }) => [`${wire.module}-${wire.modulePin}`, color]))} />
      <figcaption className="mt-3 max-w-3xl text-sm leading-6 text-gray-400">{t('edgeBuilds.wiring.caption')}</figcaption>
    </figure>
  );
}

/** The same wiring as rows, in the drawing's colours: the only form on a phone, and a checklist on a desk. */
function WireTable({ build, colors }: { build: EdgeBuild; colors: Map<string, string> }) {
  const { t } = useTranslation();
  return (
    <div className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
      {build.modules.map((module) => (
        <div key={module.id}>
          <p className="mb-1.5 text-sm font-semibold text-white">{module.label}</p>
          <ul className="space-y-1">
            {build.wires.filter((wire) => wire.module === module.id).map((wire) => (
              <li key={wire.modulePin} className="flex items-center gap-2 font-mono text-xs text-gray-200">
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: colors.get(`${wire.module}-${wire.modulePin}`) }} />
                {wire.boardPin} → {wire.modulePin}
              </li>
            ))}
          </ul>
          {module.note && <p className="mt-1 text-xs leading-5 text-gray-400">{t(module.note)}</p>}
        </div>
      ))}
    </div>
  );
}

/**
 * Where the board's 5 V comes from: down the column on a phone, left to right
 * from `sm`. Each arrow belongs to the stage after it, so a wrapped row never
 * leaves an arrow hanging at the end of a line.
 */
export function EdgePowerPath({ stages }: { stages: EdgePowerStage[] }) {
  const { t } = useTranslation();
  return (
    <ol className="flex flex-col items-start gap-1 text-sm sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-2 sm:gap-y-3">
      {stages.map((stage, index) => (
        <li key={stage} className="flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-2">
          {index > 0 && <ChevronRight aria-hidden className="ml-4 h-4 w-4 shrink-0 rotate-90 text-cyan-300 sm:ml-0 sm:rotate-0" />}
          <span className="rounded-lg border border-white/15 bg-white/5 px-3 py-2">
            <span className="block whitespace-nowrap font-medium text-white">{t(`edgeBuilds.power.${stage}.name`)}</span>
            <span className="block text-xs text-gray-400">{t(`edgeBuilds.power.${stage}.value`)}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}
