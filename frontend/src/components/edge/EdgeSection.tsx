import { useEffect, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { fetchEdgeKits, type EdgeKit } from '../../utils/edgeFirmware';
import { EdgeBuildConfigurator } from './EdgeBuildConfigurator';
import { EdgeKitGuide } from './EdgeKitGuide';
import { EdgeLineup } from './EdgeLineup';
import { EdgeMap } from './EdgeMap';
import { EdgeRuntimeInstall } from './EdgeRuntimeInstall';

const BENEFITS = ['slots', 'oneNode', 'keys'] as const;
const PRINTERS = ['happyHare', 'klipper', 'qidi', 'flashforgeStation', 'flashforgeSingle', 'bambu'] as const;
const STEPS = ['printer', 'install', 'pair'] as const;
const PATHS = [
  { key: 'tags', href: '#edge-kit', action: 'toKit', chip: 'border-amber-300/40 bg-amber-400/10 text-amber-200' },
  { key: 'printer', href: '#edge-install', action: 'toInstall', chip: 'border-cyan-300/40 bg-cyan-400/10 text-cyan-200' },
] as const;
const OTHER_WAYS = [
  { key: 'bambu', to: '/download' },
  { key: 'octoprint', to: '/download/octoprint' },
  { key: 'slicerOpen', to: '/download' },
] as const;

const heading = 'mb-2 text-2xl font-bold text-white md:text-3xl';
const lead = 'mb-6 max-w-2xl text-base leading-7 text-gray-300';

export function EdgeSection() {
  const { t } = useTranslation();
  const [kits, setKits] = useState<EdgeKit[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    // No kits is a normal answer; the page still explains Edge itself.
    fetchEdgeKits(controller.signal).then(setKits).catch(() => undefined);
    return () => controller.abort();
  }, []);

  return (
    <>
      <header className="mb-8 max-w-3xl md:mb-10">
        <h1 className="mb-4 text-4xl font-bold tracking-tight text-white md:text-5xl">{t('edgeSection.title')}</h1>
        <p className="mb-3 text-lg leading-8 text-gray-100 md:text-xl">{t('edgeSection.lead')}</p>
        <p className="text-base leading-7 text-gray-300">{t('edgeSection.forms')}</p>
      </header>

      <section aria-labelledby="edge-paths" className="mb-14 md:mb-20">
        <h2 id="edge-paths" className={heading}>{t('edgeSection.pathsTitle')}</h2>
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {PATHS.map(({ key, href, action, chip }) => (
            <div key={key} className="flex flex-col rounded-2xl border border-white/10 bg-white/[0.03] p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-xl font-semibold text-white">{t(`edgeSection.paths.${key}.title`)}</h3>
                <span className={`rounded-full border px-3 py-0.5 text-xs font-semibold ${chip}`}>
                  {t(`edgeSection.paths.${key}.status`)}
                </span>
              </div>
              <p className="mt-2 flex-1 text-sm leading-6 text-gray-300">{t(`edgeSection.paths.${key}.text`)}</p>
              <a
                href={href}
                className="mt-4 inline-flex items-center self-start rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-purple-500"
              >
                {t(`edgeSection.${action}`)}
              </a>
            </div>
          ))}
        </div>
      </section>

      {/* The device being built now leads the page: what it is, its files and its
          assembly come before the program and the builds that are only designed. */}
      {kits.length > 0 && (
        <div id="edge-kit" className="scroll-mt-24">
          {kits.map((kit) => <EdgeKitGuide key={kit.id} kit={kit} />)}
        </div>
      )}

      <EdgeMap />

      <section className="mb-14 md:mb-20">
        <h2 className={heading}>{t('edgeSection.whyTitle')}</h2>
        <div className="mt-6 grid gap-x-10 gap-y-6 md:grid-cols-3">
          {BENEFITS.map((benefit) => (
            <div key={benefit} className="border-t border-cyan-300/40 pt-4">
              <h3 className="mb-2 text-lg font-semibold text-white">{t(`edgeSection.benefits.${benefit}.title`)}</h3>
              <p className="text-sm leading-6 text-gray-300">{t(`edgeSection.benefits.${benefit}.text`)}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-14 md:mb-20">
        <h2 className={heading}>{t('edgeSection.supportTitle')}</h2>
        <p className={lead}>{t('edgeSection.supportLead')}</p>
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 text-gray-300">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium">{t('edgeSection.supportPrinter')}</th>
                <th scope="col" className="px-4 py-3 font-medium">{t('edgeSection.supportSees')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {PRINTERS.map((printer) => (
                <tr key={printer}>
                  <th scope="row" className="px-4 py-3 align-top font-medium text-white">{t(`edgeSection.printers.${printer}.name`)}</th>
                  <td className="px-4 py-3 leading-6 text-gray-300">{t(`edgeSection.printers.${printer}.sees`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h3 className="mb-3 mt-8 text-lg font-semibold text-white">{t('edgeSection.otherTitle')}</h3>
        <ul className="space-y-2 text-sm leading-6 text-gray-300">
          {OTHER_WAYS.map(({ key, to }) => (
            <li key={key}>
              {t(`edgeSection.other.${key}.text`)}{' '}
              <Link to={to} className="text-purple-300 underline">{t(`edgeSection.other.${key}.link`)}</Link>
            </li>
          ))}
        </ul>
      </section>

      <section id="edge-install" className="mb-14 scroll-mt-24 md:mb-20">
        <h2 className={heading}>{t('edgeSection.installTitle')}</h2>
        <p className={lead}>{t('edgeSection.installLead')}</p>
        <ol className="mb-8 grid gap-6 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step}>
              <p className="mb-1 text-3xl font-bold text-cyan-300">{index + 1}</p>
              <p className="text-sm leading-6 text-gray-200">{t(`edgeSection.steps.${step}`)}</p>
            </li>
          ))}
        </ol>
        <EdgeRuntimeInstall />
        <p className="mt-4 max-w-2xl text-sm leading-6 text-gray-400">{t('edgeSection.privacy')}</p>
      </section>

      <details
        id={kits.length === 0 ? 'edge-kit' : undefined}
        className="group mb-12 scroll-mt-24 rounded-2xl border border-white/10 bg-white/[0.03]"
      >
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 rounded-2xl p-5 marker:hidden focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-purple-400 [&::-webkit-details-marker]:hidden">
          <span>
            <span className="block text-xl font-semibold text-white">{t('edgeSection.laterTitle')}</span>
            <span className="mt-1 block text-sm text-gray-400">{t('edgeSection.laterLead')}</span>
          </span>
          <ChevronDown aria-hidden="true" className="h-5 w-5 shrink-0 text-gray-400 transition-transform group-open:rotate-180" />
        </summary>
        <div className="border-t border-white/10 p-5">
          <EdgeLineup />
          <EdgeBuildConfigurator />
        </div>
      </details>
    </>
  );
}
