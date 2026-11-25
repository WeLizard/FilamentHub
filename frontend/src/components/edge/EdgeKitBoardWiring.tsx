import { useTranslation } from 'react-i18next';
import type { EdgeNfcPins } from '../../utils/edgeFirmware';
import { DIAGRAM_DETAIL, DIAGRAM_GROUND, DIAGRAM_INK, DIAGRAM_MUTED, DIAGRAM_PART, DIAGRAM_POWER } from './edgeDiagram';

type Point = [number, number];

// Both boards seen from the component side, pads in the order they sit on the
// boards. The drawing is a wiring aid, not to scale.
const BOARD_LEFT = ['5', '6', '7', '8', '9', '10', '20', '21'];
const BOARD_RIGHT = ['5V', 'G', '3.3', '4', '3', '2', '1', '0'];
const READER = ['+5V', '+3.3V', 'RST', 'NSS', 'MOSI', 'MISO', 'SCK', 'BUSY', 'GND', 'GPIO', 'IRQ', 'AUX', 'REQ'];
const COLORS: Record<string, string> = {
  '+5V': DIAGRAM_POWER.v5,
  '+3.3V': DIAGRAM_POWER.v33,
  RST: '#b088e0',
  NSS: '#4b9be6',
  MOSI: '#3fbf92',
  MISO: '#3cc0d6',
  SCK: '#8087f2',
  BUSY: '#dd7cc4',
  GND: DIAGRAM_POWER.gnd,
};
const PANEL = DIAGRAM_GROUND;
const UNUSED = '#6b7686';
const boardY = (row: number) => 205 + row * 38;
const readerY = (row: number) => 185 + row * 24;

/** An orthogonal polyline with a short rounded turn at every bend. */
function route(points: Point[], radius = 5): string {
  const parts = [`M${points[0][0]} ${points[0][1]}`];
  for (let at = 1; at < points.length - 1; at++) {
    const [before, corner, after] = [points[at - 1], points[at], points[at + 1]];
    const into: Point = [Math.sign(corner[0] - before[0]), Math.sign(corner[1] - before[1])];
    const out: Point = [Math.sign(after[0] - corner[0]), Math.sign(after[1] - corner[1])];
    parts.push(`L${corner[0] - into[0] * radius} ${corner[1] - into[1] * radius}`);
    parts.push(`Q${corner[0]} ${corner[1]} ${corner[0] + out[0] * radius} ${corner[1] + out[1] * radius}`);
  }
  const last = points[points.length - 1];
  parts.push(`L${last[0]} ${last[1]}`);
  return parts.join(' ');
}

/** The pin map this drawing was laid out for; another map falls back to the plain list. */
export function boardWiringFits(pins: EdgeNfcPins): boolean {
  return pins.sck === 4 && pins.miso === 5 && pins.mosi === 6
    && pins.nss === 7 && pins.busy === 0 && pins.rst === 1;
}

export function EdgeKitBoardWiring({ pins }: { pins: EdgeNfcPins }) {
  const { t } = useTranslation();
  // Reader pad -> board pad, numbered in the reader's own order.
  const boardPad: Record<string, string> = {
    '+5V': '5V',
    '+3.3V': '3.3',
    RST: String(pins.rst),
    NSS: String(pins.nss),
    MOSI: String(pins.mosi),
    MISO: String(pins.miso),
    SCK: String(pins.sck),
    BUSY: String(pins.busy),
    GND: 'G',
  };
  const wires = READER.filter((pad) => pad in boardPad).map((pad, index) => ({
    reader: pad,
    board: boardPad[pad],
    number: index + 1,
    color: COLORS[pad],
    y: readerY(READER.indexOf(pad)),
  }));
  const byBoardPad = new Map(wires.map((wire) => [wire.board, wire]));
  const wire = (pad: string) => wires.find((item) => item.reader === pad)!;

  // Pads on the board's left edge go round the top in their own lanes; pads on
  // the right edge take one bend each. Later paths cross over earlier ones.
  const overTop = (pad: string, lane: number): Point[] => {
    const item = wire(pad);
    const [laneX, laneY, dropX] = [58 + lane * 17, 105 + lane * 15, 520 + lane * 15];
    const y = boardY(BOARD_LEFT.indexOf(item.board));
    return [[130, y], [laneX, y], [laneX, laneY], [dropX, laneY], [dropX, item.y], [600, item.y]];
  };
  const oneBend = (pad: string, bendX: number): Point[] => {
    const item = wire(pad);
    const y = boardY(BOARD_RIGHT.indexOf(item.board));
    return [[260, y], [bendX, y], [bendX, item.y], [600, item.y]];
  };
  const paths: { pad: string; points: Point[] }[] = [
    { pad: 'NSS', points: overTop('NSS', 0) },
    { pad: 'MOSI', points: overTop('MOSI', 1) },
    { pad: 'MISO', points: overTop('MISO', 2) },
    { pad: '+3.3V', points: oneBend('+3.3V', 326) },
    { pad: 'GND', points: oneBend('GND', 351) },
    { pad: 'RST', points: oneBend('RST', 383) },
    { pad: 'BUSY', points: oneBend('BUSY', 425) },
    { pad: 'SCK', points: oneBend('SCK', 460) },
    { pad: '+5V', points: oneBend('+5V', 315) },
  ];

  const pad = (x: number, y: number, name: string, labelX: number, anchor: 'start' | 'end') => {
    const used = byBoardPad.get(name);
    return (
      <g key={`${x}-${name}`}>
        <circle cx={x} cy={y} r={used ? 8.5 : 5} fill={used?.color ?? UNUSED} stroke={PANEL} strokeWidth={1} />
        {used && (
          <>
            <text x={x} y={y + 2.6} fontSize={7.4} fontWeight={700} textAnchor="middle" fill={PANEL}>{used.number}</text>
            <text x={labelX} y={y + 3.4} fontSize={9.4} fontWeight={700} textAnchor={anchor} fill="#fff">{name}</text>
          </>
        )}
      </g>
    );
  };

  return (
    <figure>
      <div className="rounded-2xl border border-white/10 p-3 md:p-5" style={{ backgroundColor: PANEL }}>
        <svg viewBox="44 92 780 432" role="img" aria-label={t('edgeKit.guide.wiring.title')} className="h-auto w-full">
          {paths.map(({ pad: name, points }) => (
            <g key={name} fill="none" strokeLinecap="round" strokeLinejoin="round">
              <path d={route(points)} stroke={PANEL} strokeWidth={8.5} />
              <path d={route(points)} stroke={COLORS[name]} strokeWidth={3.2} />
            </g>
          ))}

          <rect x={130} y={170} width={130} height={320} rx={9} fill={DIAGRAM_PART} stroke={DIAGRAM_INK} strokeWidth={1.25} />
          <rect x={171} y={158} width={47} height={22} rx={5} fill={DIAGRAM_DETAIL} stroke={DIAGRAM_MUTED} />
          <text x={194.5} y={196} fontSize={9.2} fontWeight={700} textAnchor="middle" fill="#fff">USB-C</text>
          <rect x={149} y={300} width={90} height={71} rx={7} fill={DIAGRAM_DETAIL} stroke={DIAGRAM_MUTED} />
          <text x={194} y={338} fontSize={10.5} fontWeight={700} textAnchor="middle" fill="#fff">ESP32-C3</text>
          {BOARD_LEFT.map((name, row) => pad(130, boardY(row), name, 147, 'start'))}
          {BOARD_RIGHT.map((name, row) => pad(260, boardY(row), name, 246, 'end'))}

          <rect x={600} y={170} width={210} height={320} rx={9} fill={DIAGRAM_PART} stroke={DIAGRAM_INK} strokeWidth={1.25} />
          {[0, 1, 2, 3, 4].map((turn) => (
            <rect
              key={turn}
              x={700 + turn * 8}
              y={221 + turn * 8}
              width={90 - turn * 16}
              height={205 - turn * 16}
              rx={2}
              fill="none"
              stroke={DIAGRAM_MUTED}
              strokeWidth={1.5}
            />
          ))}
          <rect x={648} y={296} width={43} height={42} rx={4} fill={DIAGRAM_DETAIL} stroke={DIAGRAM_MUTED} />
          <text x={669.5} y={320} fontSize={7.2} fontWeight={700} textAnchor="middle" fill="#fff">PN5180</text>
          {READER.map((name, row) => {
            const used = wires.find((item) => item.reader === name);
            const y = readerY(row);
            return (
              <g key={name}>
                <circle cx={600} cy={y} r={used ? 8 : 5} fill={used?.color ?? UNUSED} stroke={PANEL} strokeWidth={1} />
                {used && (
                  <text x={600} y={y + 2.6} fontSize={7.2} fontWeight={700} textAnchor="middle" fill={PANEL}>{used.number}</text>
                )}
                <text x={616} y={y + 3.4} fontSize={9.4} fontWeight={used ? 700 : 400} fill={used ? DIAGRAM_INK : DIAGRAM_MUTED}>{name}</text>
                {!used && <text x={664} y={y + 3.2} fontSize={7.6} fontWeight={700} fill={DIAGRAM_MUTED}>NC</text>}
              </g>
            );
          })}
          <text x={130} y={513} fontSize={10} fontWeight={600} fill={DIAGRAM_MUTED}>{t('edgeKit.guide.wiring.boardCaption')}</text>
          <text x={600} y={513} fontSize={10} fontWeight={600} fill={DIAGRAM_MUTED}>{t('edgeKit.guide.wiring.readerCaption')}</text>
        </svg>
      </div>
      <ul className="mt-4 grid gap-x-6 gap-y-1.5 text-sm text-gray-200 sm:grid-cols-3">
        {wires.map((item) => (
          <li key={item.reader} className="flex items-center gap-2">
            <span
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold"
              style={{ backgroundColor: item.color, color: PANEL }}
            >
              {item.number}
            </span>
            <span className="font-mono text-xs">
              {/^\d+$/.test(item.board) ? `GPIO${item.board}` : item.board} → {item.reader}
            </span>
          </li>
        ))}
      </ul>
      <figcaption className="mt-3 max-w-3xl text-sm leading-6 text-gray-400">{t('edgeKit.guide.wiring.note')}</figcaption>
    </figure>
  );
}
