import { useTranslation } from 'react-i18next';
import { ChevronRight, KeyRound, Layers, Monitor, Router, Smartphone } from 'lucide-react';
import { Printer3DIcon } from '../icons/Printer3DIcon';

const PRINTERS = ['klipper', 'qidi', 'flashforge'] as const;

// The arrow points down while the blocks are stacked and right once they sit in a row.
const ARROW = {
  inner: {
    row: 'sm:flex-row',
    line: 'sm:h-px sm:w-8 sm:bg-gradient-to-r',
    head: 'sm:-ml-2 sm:mt-0 sm:rotate-0',
  },
  outer: {
    row: 'lg:flex-row',
    line: 'lg:h-px lg:w-8 lg:bg-gradient-to-r',
    head: 'lg:-ml-2 lg:mt-0 lg:rotate-0',
  },
} as const;

function Flow({ place, label }: { place: keyof typeof ARROW; label?: string }) {
  const arrow = ARROW[place];
  return (
    <div className="flex flex-col items-center justify-center gap-1 py-1 text-cyan-300" aria-hidden={!label}>
      <div className={`flex flex-col items-center ${arrow.row}`}>
        <span className={`h-5 w-px bg-gradient-to-b from-cyan-300/10 to-cyan-300/80 ${arrow.line}`} />
        <ChevronRight className={`-mt-2 h-5 w-5 rotate-90 motion-safe:animate-pulse ${arrow.head}`} />
      </div>
      {label && <span className="max-w-[9rem] text-center text-xs leading-4 text-cyan-100/80">{label}</span>}
    </div>
  );
}

/** Where Edge sits: inside the person's network, between their printers and the site. */
export function EdgeMap() {
  const { t } = useTranslation();
  const outside = [
    { key: 'site', Icon: Monitor },
    { key: 'phone', Icon: Smartphone },
    { key: 'slicer', Icon: Layers },
  ] as const;

  return (
    <figure className="mb-14 md:mb-20">
      <div className="grid items-stretch gap-2 lg:grid-cols-[minmax(0,2fr)_auto_minmax(0,0.9fr)_auto_minmax(0,0.9fr)]">
        <div className="rounded-2xl border border-dashed border-white/25 p-4 md:p-5">
          <p className="mb-4 text-sm font-medium text-gray-300">{t('edgeSection.map.network')}</p>
          <div className="grid items-center gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
            <ul className="space-y-2">
              {PRINTERS.map((printer) => (
                <li key={printer} className="flex items-center gap-2 rounded-lg bg-white/5 px-3 py-2 text-sm text-gray-100">
                  <Printer3DIcon className="h-4 w-4 shrink-0 text-purple-300" />
                  {t(`edgeSection.map.printers.${printer}`)}
                </li>
              ))}
            </ul>
            <Flow place="inner" />
            <div className="rounded-xl border border-cyan-300/50 bg-cyan-400/10 p-4 shadow-[0_0_40px_rgba(34,211,238,0.12)]">
              <p className="flex items-center gap-2 text-lg font-semibold text-white">
                <Router className="h-5 w-5 shrink-0 text-cyan-300" />
                FH Edge
              </p>
              <p className="mt-2 flex items-start gap-2 text-xs leading-5 text-cyan-50/80">
                <KeyRound className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {t('edgeSection.map.keys')}
              </p>
            </div>
          </div>
        </div>

        <Flow place="outer" label={t('edgeSection.map.outbound')} />

        <div className="flex flex-col justify-center rounded-2xl bg-gradient-to-br from-purple-600 to-purple-800 p-5 shadow-lg shadow-purple-900/40">
          <p className="text-lg font-semibold text-white">FilamentHub</p>
          <p className="mt-2 text-sm leading-5 text-purple-100">{t('edgeSection.map.cloud')}</p>
        </div>

        <Flow place="outer" />

        <div className="flex flex-col justify-center rounded-2xl border border-white/10 bg-white/5 p-5">
          <p className="mb-3 text-sm font-medium text-gray-300">{t('edgeSection.map.you')}</p>
          <ul className="space-y-2 text-sm text-gray-100">
            {outside.map(({ key, Icon }) => (
              <li key={key} className="flex items-center gap-2">
                <Icon className="h-4 w-4 text-gray-400" />
                {t(`edgeSection.map.outside.${key}`)}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <figcaption className="mt-3 text-sm text-gray-400">{t('edgeSection.map.caption')}</figcaption>
    </figure>
  );
}
