import { useTranslation } from 'react-i18next';

const FILES = '/edge-kit/';
const subheading = 'mb-3 text-xl font-semibold text-white';

type LineupStatus = 'prototype' | 'design' | 'concept' | 'planned';
const DEVICES: { key: string; status: LineupStatus; image?: string }[] = [
  { key: 'tag', status: 'prototype', image: 'kit-front.webp' },
  { key: 'station', status: 'design', image: 'station-s3-front.webp' },
  { key: 'portable', status: 'design', image: 'portable-s3-front.webp' },
  { key: 'lane', status: 'concept' },
  { key: 'scales', status: 'planned' },
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
        {DEVICES.map(({ key, status, image }) => (
          <li key={key} className="flex flex-col rounded-xl border border-white/10 bg-white/[0.03] p-4">
            {image && (
              <img src={FILES + image} alt="" width={1600} height={1000} loading="lazy" className="mb-3 h-auto w-full" />
            )}
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

/** Core and a chain of lane modules: the proposed shape, not a chosen bus. */
function LaneTopology() {
  const { t } = useTranslation();
  const lanes = [0, 1, 2, 3];
  const laneX = (index: number) => 238 + index * 104;
  return (
    <figure>
      <div className="rounded-2xl border border-white/10 p-3 md:p-5" style={{ backgroundColor: '#17112e' }}>
        <svg viewBox="0 0 720 300" role="img" aria-label={t('edgeLineup.lane.title')} className="h-auto w-full">
          <rect x={20} y={70} width={150} height={110} rx={10} fill="#1d3a55" stroke="#4a6d8a" />
          <text x={95} y={108} fontSize={15} fontWeight={700} textAnchor="middle" fill="#fff">Edge Core</text>
          <text x={95} y={128} fontSize={11} textAnchor="middle" fill="#cfe3ea">ESP32-S3</text>
          <text x={95} y={146} fontSize={10} textAnchor="middle" fill="#cfe3ea">{t('edgeLineup.lane.coreRole')}</text>
          <line x1={170} y1={125} x2={laneX(0)} y2={125} stroke="#3fbf92" strokeWidth={4} />
          {lanes.map((index) => (
            <g key={index}>
              {index > 0 && <line x1={laneX(index - 1) + 76} y1={125} x2={laneX(index)} y2={125} stroke="#3fbf92" strokeWidth={4} />}
              <rect x={laneX(index)} y={88} width={76} height={74} rx={8} fill="#1f5873" stroke="#3d87a3" />
              <text x={laneX(index) + 38} y={112} fontSize={12} fontWeight={700} textAnchor="middle" fill="#fff">Lane {index === 3 ? 8 : index + 1}</text>
              <circle cx={laneX(index) + 22} cy={136} r={7} fill="#f0a13a" />
              <rect x={laneX(index) + 38} y={129} width={16} height={14} rx={3} fill="#e5e7eb" />
              <text x={laneX(index) + 38} y={176} fontSize={9.5} textAnchor="middle" fill="#cfe3ea">{t('edgeLineup.lane.module')}</text>
            </g>
          ))}
          <text x={laneX(2) + 90} y={130} fontSize={16} fontWeight={700} textAnchor="middle" fill="#9fd0dc">…</text>
          <rect x={laneX(3) + 80} y={113} width={20} height={24} rx={3} fill="#dd7cc4" />
          <text x={laneX(3) + 90} y={154} fontSize={9.5} textAnchor="middle" fill="#f5d0ea">120 Ω</text>

          <text x={20} y={222} fontSize={11} fontWeight={700} fill="#fff">{t('edgeLineup.lane.cable')}</text>
          {CHAIN_PINS.map((pin, index) => (
            <g key={`${pin}-${index}`}>
              <rect x={20 + index * 70} y={232} width={62} height={26} rx={5} fill="#28435a" stroke="#5d7a90" />
              <text x={51 + index * 70} y={249} fontSize={11} fontWeight={700} textAnchor="middle" fill="#fff" fontFamily="monospace">{pin}</text>
            </g>
          ))}
          <line x1={480} y1={245} x2={700} y2={245} stroke="#a3b1bd" strokeWidth={2} strokeDasharray="6 5" />
          <text x={590} y={236} fontSize={10} textAnchor="middle" fill="#cfe3ea">{t('edgeLineup.lane.klipper')}</text>
        </svg>
      </div>
      <figcaption className="mt-3 max-w-3xl text-sm leading-6 text-gray-400">{t('edgeLineup.lane.caption')}</figcaption>
    </figure>
  );
}
