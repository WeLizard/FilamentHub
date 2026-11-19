import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';
import { EDGE_INSTALL_GUIDE_URL, fetchEdgeKits, type EdgeKit } from '../../utils/edgeFirmware';
import { EdgeKitGuide } from './EdgeKitGuide';
import { EdgeMap } from './EdgeMap';

const BENEFITS = ['slots', 'oneNode', 'keys'] as const;
const FORMS = ['linux', 'docker', 'homeAssistant', 'kit'] as const;
const PRINTERS = ['happyHare', 'klipper', 'qidi', 'flashforgeStation', 'flashforgeSingle'] as const;
const STEPS = ['printer', 'install', 'pair'] as const;
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
        <p className="mb-6 text-base leading-7 text-gray-300">{t('edgeSection.forms')}</p>
        <div className="flex flex-wrap gap-3">
          <a href="#edge-install" className="inline-flex items-center rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-purple-500">
            {t('edgeSection.toInstall')}
          </a>
          <a href="#edge-kit" className="inline-flex items-center rounded-lg border border-white/15 bg-white/5 px-4 py-2 text-sm font-medium text-gray-100 transition-all hover:bg-white/10">
            {t('edgeSection.toKit')}
          </a>
        </div>
      </header>

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
        <dl className="mb-8 divide-y divide-white/10 border-y border-white/10">
          {FORMS.map((form) => (
            <div key={form} className="grid gap-1 py-4 md:grid-cols-[14rem_minmax(0,1fr)] md:gap-6">
              <dt className="font-semibold text-white">{t(`edgeSection.where.${form}.name`)}</dt>
              <dd className="text-sm leading-6 text-gray-300">{t(`edgeSection.where.${form}.text`)}</dd>
            </div>
          ))}
        </dl>
        <ol className="mb-6 grid gap-6 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step}>
              <p className="mb-1 text-3xl font-bold text-cyan-300">{index + 1}</p>
              <p className="text-sm leading-6 text-gray-200">{t(`edgeSection.steps.${step}`)}</p>
            </li>
          ))}
        </ol>
        <a
          href={EDGE_INSTALL_GUIDE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-purple-500"
        >
          {t('edgeSection.installGuide')}
          <ExternalLink className="h-4 w-4" />
        </a>
        <p className="mt-4 max-w-2xl text-sm leading-6 text-gray-400">{t('edgeSection.privacy')}</p>
      </section>

      {kits.map((kit) => <EdgeKitGuide key={kit.id} kit={kit} />)}
    </>
  );
}
