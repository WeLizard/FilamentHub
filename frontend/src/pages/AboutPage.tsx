import { ArrowLeft, CircleDot, Heart, Info } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { SEOHead } from '../components/SEOHead';
import { externalUrl } from '../utils/externalUrl';
import { SUPPORT_URL } from '../utils/support';

const ROADMAP_SECTIONS = [
  { key: 'working', accent: 'text-emerald-400' },
  { key: 'progress', accent: 'text-amber-400' },
  { key: 'next', accent: 'text-slate-500' },
] as const;

export const AboutPage = () => {
  const { t } = useTranslation();
  const supportHref = externalUrl(SUPPORT_URL);

  return (
    <>
      <SEOHead title={t('aboutPage.title')} description={t('aboutPage.intro')} url="/about" type="website" />
      <main className="relative z-10 mx-auto max-w-4xl px-4 py-8 sm:px-6">
          <Link
            to="/"
            className="mb-4 inline-flex items-center gap-2 text-purple-400 transition-colors hover:text-purple-300"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>{t('legalDocument.backHome')}</span>
          </Link>

          <header className="mb-8 flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-r from-purple-500 to-indigo-500 shadow-lg shadow-purple-500/25">
              <Info className="h-6 w-6 text-white" />
            </div>
            <h1 className="text-3xl font-bold text-white">{t('aboutPage.title')}</h1>
          </header>

          <div className="space-y-3 text-slate-300">
            <p>{t('aboutPage.intro')}</p>
            <p>{t('aboutPage.free')}</p>
          </div>

          <section className="mt-10 space-y-6">
            <h2 className="text-xl font-semibold text-white">{t('aboutPage.roadmapTitle')}</h2>

            {ROADMAP_SECTIONS.map(({ key, accent }) => {
              const items = t(`aboutPage.${key}.items`, { returnObjects: true });
              return (
                <div key={key} className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                  <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
                    {t(`aboutPage.${key}.title`)}
                  </h3>
                  <ul className="space-y-2">
                    {(Array.isArray(items) ? items : []).map((item: string) => (
                      <li key={item} className="flex gap-2.5 text-sm text-slate-300">
                        <CircleDot className={`mt-0.5 h-4 w-4 flex-shrink-0 ${accent}`} />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}

            <p className="text-sm text-slate-500">{t('aboutPage.roadmapNote')}</p>
          </section>

          {supportHref && (
            <section className="mt-10 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
              <h2 className="mb-3 flex items-center gap-2 text-xl font-semibold text-white">
                <Heart className="h-5 w-5 text-rose-400" />
                {t('aboutPage.support.title')}
              </h2>
              <p className="text-sm text-slate-300">{t('aboutPage.support.text')}</p>
              <p className="mt-2 text-sm text-slate-500">{t('aboutPage.support.note')}</p>
              <a
                href={supportHref}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-4 inline-flex items-center gap-2 rounded-xl bg-rose-500/90 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-rose-500"
              >
                <Heart className="h-4 w-4" />
                {t('aboutPage.support.action')}
              </a>
            </section>
          )}
      </main>
    </>
  );
};
