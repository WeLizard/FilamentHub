import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, Router } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { EDGE_INSTALL_GUIDE_URL, fetchEdgeKits, type EdgeKit } from '../../utils/edgeFirmware';
import { EdgeKitInstaller } from './EdgeKitInstaller';

const STEPS = ['printer', 'install', 'pair'] as const;

export function EdgeSection() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [kits, setKits] = useState<EdgeKit[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    // No kits is a normal answer; the section still explains Edge itself.
    fetchEdgeKits(controller.signal).then(setKits).catch(() => undefined);
    return () => controller.abort();
  }, []);

  // A kit that has not passed hardware acceptance is offered to administrators only.
  const offered = kits.filter((kit) => kit.status === 'released' || user?.role === 'admin');

  return (
    <>
      <div className="mb-8 text-center md:mb-12">
        <div className="mb-4 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-purple-500 shadow-lg shadow-cyan-500/25 md:h-16 md:w-16 md:rounded-2xl">
            <Router className="h-6 w-6 text-white md:h-8 md:w-8" />
          </div>
          <h1 className="text-center text-2xl font-bold text-white sm:text-3xl md:text-4xl">{t('edgeSection.title')}</h1>
        </div>
        <p className="mx-auto max-w-2xl text-base text-gray-300 md:text-xl">{t('edgeSection.subtitle')}</p>
      </div>

      <section className="glass-panel-subtle mb-12 rounded-2xl border border-white/10 p-6 md:p-8">
        <h2 className="mb-3 text-2xl font-bold text-white">{t('edgeSection.softwareTitle')}</h2>
        <p className="mb-2 max-w-3xl text-sm leading-6 text-gray-300 md:text-base">{t('edgeSection.softwareDesc')}</p>
        <p className="mb-6 max-w-3xl text-sm leading-6 text-gray-300 md:text-base">{t('edgeSection.supported')}</p>
        <ol className="mb-6 grid gap-4 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step} className="rounded-xl border border-white/10 bg-white/5 p-4">
              <p className="mb-1 text-sm font-semibold text-purple-300">{index + 1}</p>
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
        <p className="mt-4 max-w-3xl text-xs leading-5 text-gray-400">{t('edgeSection.privacy')}</p>
      </section>

      {offered.map((kit) => (
        <section key={kit.id} className="mb-12 rounded-2xl border border-cyan-400/20 bg-slate-950/45 p-6 md:p-8">
          <div className="mb-2 flex flex-wrap items-center gap-3">
            <h2 className="text-2xl font-bold text-white">{t('edgeSection.kitTitle')}</h2>
            {kit.status !== 'released' && (
              <span className="rounded-full border border-amber-300/40 bg-amber-400/10 px-3 py-0.5 text-xs font-semibold text-amber-200">
                {t(`edgeSection.kitStatus.${kit.status}`)}
              </span>
            )}
          </div>
          <p className="mb-2 max-w-3xl text-sm leading-6 text-gray-300 md:text-base">{t('edgeSection.kitDesc')}</p>
          {kit.status !== 'released' && (
            <p className="mb-5 max-w-3xl text-sm leading-6 text-amber-200/90">{t('edgeSection.kitAdminOnly')}</p>
          )}
          <EdgeKitInstaller kit={kit} />
        </section>
      ))}
    </>
  );
}
