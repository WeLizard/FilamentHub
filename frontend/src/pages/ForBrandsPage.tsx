import { ArrowLeft, ArrowRight, Factory } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { SEOHead } from '../components/SEOHead';
import { useAuth } from '../contexts/AuthContext';
import { MANUFACTURER_STEPS, manufacturerGuideLink } from '../data/capabilities';
import { normalizeSiteLocale } from '../utils/siteLocale';
import { PARTNERS_EMAIL } from '../utils/support';

interface ChangeRow {
  now: string;
  with: string;
}

// What a manufacturer can put on the packaging, with how far along each is.
const TAG_OPTIONS = [
  { id: 'qr', status: 'working', chip: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200' },
  { id: 'open', status: 'progress', chip: 'border-amber-400/30 bg-amber-400/10 text-amber-200' },
  { id: 'write', status: 'next', chip: 'border-white/20 bg-white/5 text-slate-300' },
] as const;

/**
 * For a manufacturer deciding whether this is worth their time: first what it
 * changes for them and their buyers, then what it looks like, then the work.
 */
export const ForBrandsPage = () => {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const locale = normalizeSiteLocale(i18n.resolvedLanguage || i18n.language) || 'en';
  const rowValues = t('forBrands.rows', { returnObjects: true });
  const rows = Array.isArray(rowValues) ? rowValues as ChangeRow[] : [];

  return (
    <>
      <SEOHead
        title={t('forBrands.seoTitle')}
        description={t('forBrands.seoDescription')}
        url="/for-brands"
        type="website"
      />
      <main className="relative z-10 mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <Link
          to="/"
          className="mb-4 inline-flex items-center gap-2 text-purple-400 transition-colors hover:text-purple-300"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>{t('legalDocument.backHome')}</span>
        </Link>

        <header className="mb-4 flex items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-r from-purple-500 to-indigo-500 shadow-lg shadow-purple-500/25">
            <Factory className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-white">{t('forBrands.title')}</h1>
        </header>
        <p className="max-w-3xl text-lg leading-8 text-slate-200">{t('forBrands.lead')}</p>

        <section className="mt-10" aria-labelledby="for-brands-change">
          <h2 id="for-brands-change" className="text-xl font-semibold text-white">{t('forBrands.changeTitle')}</h2>
          <div className="mt-4 overflow-hidden rounded-2xl border border-white/10">
            <table className="w-full text-left text-sm">
              <thead className="hidden bg-white/5 sm:table-header-group">
                <tr>
                  <th scope="col" className="w-1/2 px-5 py-3 font-medium text-slate-400">{t('forBrands.now')}</th>
                  <th scope="col" className="w-1/2 px-5 py-3 font-medium text-emerald-300">{t('forBrands.with')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10">
                {rows.map((row) => (
                  <tr key={row.now} className="flex flex-col sm:table-row">
                    <td className="px-5 pt-4 align-top leading-6 text-slate-400 sm:py-4">
                      <span className="mb-1 block text-xs font-medium text-slate-500 sm:hidden">{t('forBrands.now')}</span>
                      {row.now}
                    </td>
                    <td className="px-5 pb-4 pt-2 align-top leading-6 text-white sm:py-4">
                      <span className="mb-1 block text-xs font-medium text-emerald-300 sm:hidden">{t('forBrands.with')}</span>
                      {row.with}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <figure className="mt-10">
          <img
            src={`/brand/for-brands-brand-page.${locale}.webp`}
            alt={t('forBrands.figureAlt')}
            width={1268}
            height={727}
            loading="lazy"
            className="h-auto w-full rounded-2xl border border-white/10"
          />
          <figcaption className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
            {t('forBrands.figureCaption')}
          </figcaption>
        </figure>

        <section className="mt-10" aria-labelledby="for-brands-tags">
          <h2 id="for-brands-tags" className="text-xl font-semibold text-white">{t('forBrands.tags.title')}</h2>
          <p className="mt-1 text-sm text-slate-400">{t('forBrands.tags.lead')}</p>
          <ul className="mt-4 divide-y divide-white/10 rounded-2xl border border-white/10 bg-white/[0.03]">
            {TAG_OPTIONS.map(({ id, status, chip }) => (
              <li key={id} className="p-5">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                  <h3 className="font-semibold text-white">{t(`forBrands.tags.items.${id}.title`)}</h3>
                  <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${chip}`}>
                    {t(status === 'working' ? 'featuresPage.workingLabel' : `aboutPage.${status}.title`)}
                  </span>
                </div>
                <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-300">{t(`forBrands.tags.items.${id}.text`)}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-10" aria-labelledby="for-brands-steps">
          <h2 id="for-brands-steps" className="text-xl font-semibold text-white">{t('forBrands.stepsTitle')}</h2>
          <p className="mt-1 text-sm text-slate-400">{t('forBrands.stepsLead')}</p>
          <ol className="mt-4 divide-y divide-white/10 rounded-2xl border border-white/10 bg-white/[0.03]">
            {MANUFACTURER_STEPS.map((step, index) => (
              <li key={step.id} className="flex flex-col gap-1 p-5 sm:flex-row sm:gap-5">
                <span className="w-6 shrink-0 text-lg font-semibold text-purple-300" aria-hidden="true">{index + 1}</span>
                <div className="min-w-0 flex-1">
                  <h3 className="font-semibold text-white">{t(`wikiPage.manufacturerJourney.${step.id}`)}</h3>
                  <p className="mt-1 text-sm leading-6 text-slate-300">{t(`forBrands.steps.${step.id}`)}</p>
                </div>
                <Link
                  to={manufacturerGuideLink(step)}
                  className="inline-flex shrink-0 items-center gap-2 self-start text-sm font-semibold text-purple-300 transition-colors hover:text-purple-200"
                >
                  {t('forBrands.stepAction')}
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </li>
            ))}
          </ol>
        </section>

        <section className="mt-10 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="text-xl font-semibold text-white">{t('forBrands.startTitle')}</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">{t('forBrands.startText')}</p>
          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-3">
            {!user && (
              <Link
                to="/?auth=login"
                className="inline-flex items-center rounded-xl bg-purple-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-purple-500"
              >
                {t('forBrands.startAction')}
              </Link>
            )}
            <p className="text-sm text-slate-300">
              {t('forBrands.contactText')}{' '}
              <a
                href={`mailto:${PARTNERS_EMAIL}`}
                className="text-purple-300 underline underline-offset-2 hover:text-purple-200"
              >
                {PARTNERS_EMAIL}
              </a>
            </p>
          </div>
        </section>
      </main>
    </>
  );
};
