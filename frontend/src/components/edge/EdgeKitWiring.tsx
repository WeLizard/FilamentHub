import { useTranslation } from 'react-i18next';
import type { EdgeNfcPins } from '../../utils/edgeFirmware';

/** The nine wires between the board and the reader as a plain list, one per row. */
export function EdgeKitWiring({ pins }: { pins: EdgeNfcPins }) {
  const { t } = useTranslation();
  const wires = [
    { board: '5V', reader: '+5V', color: '#f0665e' },
    { board: '3.3', reader: '+3.3V', color: '#f0a13a' },
    { board: `GPIO${pins.rst}`, reader: 'RST', color: '#b088e0' },
    { board: `GPIO${pins.nss}`, reader: 'NSS', color: '#4b9be6' },
    { board: `GPIO${pins.mosi}`, reader: 'MOSI', color: '#3fbf92' },
    { board: `GPIO${pins.miso}`, reader: 'MISO', color: '#3cc0d6' },
    { board: `GPIO${pins.sck}`, reader: 'SCK', color: '#8087f2' },
    { board: `GPIO${pins.busy}`, reader: 'BUSY', color: '#dd7cc4' },
    { board: 'G', reader: 'GND', color: '#a3b1bd' },
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
            <span className="h-0.5 rounded-full" style={{ backgroundColor: wire.color }} />
            <span className={`${pin} text-right`}>{wire.reader}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
