import type { LucideIcon } from 'lucide-react';
import { DIAGRAM_GROUND, DIAGRAM_INK, DIAGRAM_MUTED, DIAGRAM_PART, DIAGRAM_SIGNAL } from './edgeDiagram';
import { Cable, Weight } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const FILES = '/edge-kit/';
const subheading = 'mb-3 text-xl font-semibold text-white';

type LineupStatus = 'prototype' | 'design' | 'concept' | 'planned';
// A device without a modelled case shows its icon in the same box, so every card lines up.
const DEVICES: { key: string; status: LineupStatus; image?: string; Icon?: LucideIcon }[] = [
  { key: 'tag', status: 'prototype', image: 'kit-front.webp' },
  { key: 'station', status: 'design', image: 'station-s3-front.webp' },
  { key: 'portable', status: 'design', image: 'portable-s3-front.webp' },
  { key: 'lane', status: 'concept', Icon: Cable },
  { key: 'scales', status: 'planned', Icon: Weight },
];
const STATUS_STYLE: Record<LineupStatus, string> = {
  prototype: 'border-amber-300/40 bg-amber-400/10 text-amber-200',
  design: 'border-sky-300/40 bg-sky-400/10 text-sky-200',
  concept: 'border-violet-300/40 bg-violet-400/10 text-violet-200',
  planned: 'border-white/20 bg-white/5 text-gray-300',
};

const READERS = ['pn5180', 'pn532', 'rc522', 'phone'] as const;
const TAG_KINDS = ['ntag', 'mifare', 'nfcv'] as const;
const MOUNT_TIPS = ['metal', 'distance', 'heat', 'inserts', 'test'] as const;

export function EdgeLineup() {
  const { t } = useTranslation();
  return (
    <div className="mb-14">
      <h3 className="mb-2 text-2xl font-bold text-white">{t('edgeLineup.title')}</h3>
      <p className="mb-6 max-w-3xl text-base leading-7 text-gray-300">{t('edgeLineup.lead')}</p>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {DEVICES.map(({ key, status, image, Icon }) => (
          <li key={key} className="flex min-w-0 flex-col rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="mb-3 aspect-[16/10]">
              {image ? (
                <img src={FILES + image} alt="" width={1600} height={1000} loading="lazy" className="h-full w-full object-contain" />
              ) : Icon && (
                <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-white/15">
                  <Icon aria-hidden className="h-12 w-12 text-violet-300/50" strokeWidth={1.25} />
                </div>
              )}
            </div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h4 className="text-lg font-semibold text-white">{t(`edgeLineup.devices.${key}.name`)}</h4>
              <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLE[status]}`}>
                {t(`edgeLineup.status.${status}`)}
              </span>
            </div>
            <p className="text-sm leading-6 text-gray-300">{t(`edgeLineup.devices.${key}.text`)}</p>
          </li>
        ))}
      </ul>

      <div className="mt-12">
        <h4 className={subheading}>{t('edgeLineup.lane.title')}</h4>
        <p className="mb-4 max-w-3xl text-sm leading-6 text-gray-300">{t('edgeLineup.lane.text')}</p>
        <LaneTopology />
      </div>

      <div className="mt-12">
        <h4 className={subheading}>{t('edgeLineup.readers.title')}</h4>
        <p className="mb-4 max-w-3xl text-sm leading-6 text-gray-300">{t('edgeLineup.readers.lead')}</p>
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 text-gray-300">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium">{t('edgeLineup.readers.reader')}</th>
                {TAG_KINDS.map((kind) => (
                  <th key={kind} scope="col" className="px-4 py-3 font-medium">{t(`edgeLineup.readers.kinds.${kind}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {READERS.map((reader) => (
                <tr key={reader}>
                  <th scope="row" className="px-4 py-3 align-top font-medium text-white">{t(`edgeLineup.readers.rows.${reader}.name`)}</th>
                  {TAG_KINDS.map((kind) => (
                    <td key={kind} className="px-4 py-3 align-top leading-6 text-gray-300">{t(`edgeLineup.readers.rows.${reader}.${kind}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-gray-400">{t('edgeLineup.readers.note')}</p>
      </div>

      <div className="mt-12">
        <h4 className={subheading}>{t('edgeLineup.mount.title')}</h4>
        <ul className="grid gap-x-10 gap-y-3 text-sm leading-6 text-gray-300 md:grid-cols-2">
          {MOUNT_TIPS.map((tip) => (
            <li key={tip} className="border-l-2 border-cyan-300/40 pl-3">
              <span className="font-semibold text-white">{t(`edgeLineup.mount.tips.${tip}.title`)}. </span>
              {t(`edgeLineup.mount.tips.${tip}.text`)}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

const CHAIN_PINS = ['V+', 'GND', 'CANH', 'CANL', 'CHAIN', 'GND'];

const INK = DIAGRAM_INK;
const MUTED = DIAGRAM_MUTED;
const SIGNAL = DIAGRAM_SIGNAL;
const PANEL = DIAGRAM_PART;
const LANE_WIDTH = 84;
const BUS_Y = 150;
// Three modules in a row, a gap that stands for the ones not drawn, the last.
const LANES = [
  { number: 1, x: 214 },
  { number: 2, x: 318 },
  { number: 3, x: 422 },
  { number: 8, x: 566 },
];

/** A button, an indicator and a filament sensor: what every lane module carries. */
function LaneParts({ x, y }: { x: number; y: number }) {
  return (
    <g>
      <circle cx={x - 18} cy={y} r={5} fill="none" stroke={INK} strokeWidth={1.25} />
      <circle cx={x} cy={y} r={5} fill="none" stroke={MUTED} strokeWidth={1} />
      <circle cx={x} cy={y} r={2.5} fill={SIGNAL} />
      <rect x={x + 13} y={y - 5} width={10} height={10} rx={2} fill="none" stroke={INK} strokeWidth={1.25} />
      <line x1={x + 18} y1={y - 9} x2={x + 18} y2={y + 9} stroke={MUTED} strokeWidth={1} />
    </g>
  );
}

/** Core and a chain of lane modules: the proposed shape, not a chosen bus. */
function LaneTopology() {
  const { t } = useTranslation();
  const last = LANES[LANES.length - 1];
  const terminator = last.x + LANE_WIDTH + 18;
  return (
    <figure>
      <div className="rounded-2xl border border-white/10 p-3 md:p-5" style={{ backgroundColor: DIAGRAM_GROUND }}>
        <svg viewBox="0 0 760 344" role="img" aria-label={t('edgeLineup.lane.title')} className="h-auto w-full">
          {/* The printer's own bus runs past the chain and never joins it. */}
          <line x1={24} y1={36} x2={736} y2={36} stroke={MUTED} strokeWidth={1.5} strokeDasharray="7 6" />
          <text x={24} y={24} fontSize={12} fill={MUTED}>{t('edgeLineup.lane.klipper')}</text>

          <rect x={24} y={104} width={150} height={92} rx={10} fill={PANEL} stroke={INK} strokeWidth={1.25} />
          <text x={99} y={142} fontSize={16} fontWeight={700} textAnchor="middle" fill={INK}>Edge Core</text>
          <text x={99} y={161} fontSize={12} textAnchor="middle" fill={MUTED}>ESP32-S3</text>
          <text x={99} y={178} fontSize={11} textAnchor="middle" fill={MUTED}>{t('edgeLineup.lane.coreRole')}</text>

          <line x1={174} y1={BUS_Y} x2={LANES[0].x} y2={BUS_Y} stroke={SIGNAL} strokeWidth={2.5} />
          {LANES.map((lane, index) => {
            const previous = LANES[index - 1];
            const centre = lane.x + LANE_WIDTH / 2;
            return (
              <g key={lane.number}>
                {previous && (
                  <line
                    x1={previous.x + LANE_WIDTH}
                    y1={BUS_Y}
                    x2={lane.x}
                    y2={BUS_Y}
                    stroke={SIGNAL}
                    strokeWidth={2.5}
                    strokeLinecap="round"
                    // Consecutive modules are wired solid; the dotted run skips the ones not drawn.
                    strokeDasharray={lane.number - previous.number > 1 ? '1 9' : undefined}
                  />
                )}
                {/* The spool this module watches, and its filament passing the sensor. */}
                <circle cx={centre} cy={78} r={19} fill="none" stroke={MUTED} strokeWidth={1.25} />
                <circle cx={centre} cy={78} r={6} fill="none" stroke={MUTED} strokeWidth={1.25} />
                <line x1={centre + 19} y1={78} x2={centre + 19} y2={118} stroke={MUTED} strokeWidth={1.25} />
                <rect x={lane.x} y={118} width={LANE_WIDTH} height={64} rx={8} fill={PANEL} stroke={INK} strokeWidth={1.25} />
                <text x={centre} y={141} fontSize={12} fontWeight={700} textAnchor="middle" fill={INK}>Lane {lane.number}</text>
                <LaneParts x={centre - 2} y={162} />
              </g>
            );
          })}

          {/* The chain ends in a terminating resistor, drawn as one. */}
          <polyline
            points={[
              [last.x + LANE_WIDTH, 0], [terminator, 0], [terminator + 4, -7], [terminator + 12, 7],
              [terminator + 20, -7], [terminator + 28, 7], [terminator + 32, 0], [terminator + 44, 0],
            ].map(([x, dy]) => `${x},${BUS_Y + dy}`).join(' ')}
            fill="none"
            stroke={SIGNAL}
            strokeWidth={2}
            strokeLinejoin="round"
          />
          <line x1={terminator + 44} y1={BUS_Y - 8} x2={terminator + 44} y2={BUS_Y + 8} stroke={SIGNAL} strokeWidth={2} />
          <text x={terminator + 16} y={BUS_Y + 28} fontSize={11} textAnchor="middle" fill={MUTED}>120 Ω</text>

          <LaneParts x={LANES[0].x + 20} y={222} />
          <text x={LANES[0].x + 52} y={226} fontSize={12} fill={MUTED}>{t('edgeLineup.lane.module')}</text>

          <text x={24} y={268} fontSize={12} fontWeight={600} fill={INK}>{t('edgeLineup.lane.cable')}</text>
          <rect x={24} y={280} width={CHAIN_PINS.length * 62} height={48} rx={8} fill={PANEL} stroke={MUTED} strokeWidth={1} />
          {CHAIN_PINS.map((pin, index) => {
            const x = 55 + index * 62;
            const carriesData = pin.startsWith('CAN') || pin === 'CHAIN';
            return (
              <g key={`${pin}-${index}`}>
                <circle cx={x} cy={296} r={4} fill={carriesData ? SIGNAL : 'none'} stroke={carriesData ? SIGNAL : INK} strokeWidth={1.25} />
                <text x={x} y={318} fontSize={11} fontWeight={600} textAnchor="middle" fill={INK}>{pin}</text>
              </g>
            );
          })}
        </svg>
      </div>
      <figcaption className="mt-3 max-w-3xl text-sm leading-6 text-gray-400">{t('edgeLineup.lane.caption')}</figcaption>
    </figure>
  );
}
