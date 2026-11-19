import { useTranslation } from 'react-i18next';
import type { EdgeNfcPins } from '../../utils/edgeFirmware';

interface Wire {
  board: string;
  reader: string;
  color: string;
  role: 'power' | 'ground' | 'antenna' | 'signal';
}

/** The nine wires between the board and the reader, drawn one per row. */
export function EdgeKitWiring({ pins }: { pins: EdgeNfcPins }) {
  const { t } = useTranslation();
  const wires: Wire[] = [
    { board: '3V3', reader: '+3.3V', color: '#fb923c', role: 'power' },
    { board: 'GND', reader: 'GND', color: '#9ca3af', role: 'ground' },
    { board: '5V', reader: '+5V', color: '#f87171', role: 'antenna' },
    { board: `GPIO${pins.sck}`, reader: 'SCK', color: '#facc15', role: 'signal' },
    { board: `GPIO${pins.miso}`, reader: 'MISO', color: '#4ade80', role: 'signal' },
    { board: `GPIO${pins.mosi}`, reader: 'MOSI', color: '#38bdf8', role: 'signal' },
    { board: `GPIO${pins.nss}`, reader: 'NSS', color: '#c084fc', role: 'signal' },
    { board: `GPIO${pins.busy}`, reader: 'BUSY', color: '#f472b6', role: 'signal' },
    { board: `GPIO${pins.rst}`, reader: 'RST', color: '#e5e7eb', role: 'signal' },
  ];
  const pin = 'rounded-md border border-white/15 bg-black/40 px-2 py-1 font-mono text-xs text-white';

  return (
    <div className="max-w-xl">
      <div className="mb-2 grid grid-cols-[5.5rem_minmax(2rem,1fr)_5.5rem] gap-x-3 text-sm font-medium text-gray-300">
        <span>{t('edgeKit.guide.wiring.board')}</span>
        <span />
        <span className="text-right">{t('edgeKit.guide.wiring.reader')}</span>
      </div>
      <ul className="space-y-1.5">
        {wires.map((wire) => (
          <li key={wire.reader} className="grid grid-cols-[5.5rem_minmax(2rem,1fr)_5.5rem] items-center gap-x-3">
            <span className={pin}>{wire.board}</span>
            <span className="relative flex items-center">
              <span className="h-0.5 w-full rounded-full" style={{ backgroundColor: wire.color }} />
              {wire.role === 'antenna' && (
                <span className="absolute left-1/2 -translate-x-1/2 rounded-full border border-red-300/60 bg-gray-950 px-2 py-0.5 text-[11px] text-red-100">
                  {t('edgeKit.guide.wiring.jumper')}
                </span>
              )}
            </span>
            <span className={`${pin} text-right`}>{wire.reader}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-sm leading-6 text-gray-400">{t('edgeKit.guide.wiring.unused')}</p>
    </div>
  );
}
