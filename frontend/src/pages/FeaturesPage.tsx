import { ArrowLeft, ArrowRight, CircleDot, Eye, LayoutGrid } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { SEOHead } from '../components/SEOHead';
import { useAuth } from '../contexts/AuthContext';
import {
  CAPABILITY_GROUPS,
  groupCapabilities,
  type CapabilityAccess,
} from '../data/capabilities';
import { absoluteLocalizedUrl, normalizeSiteLocale } from '../utils/siteLocale';

const ACCESS_STYLES: Record<CapabilityAccess, string> = {
  open: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  account: 'border-purple-400/30 bg-purple-400/10 text-purple-200',
  brand: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
};

export const FeaturesPage = () => {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const locale = normalizeSiteLocale(i18n.resolvedLanguage || i18n.language) || 'en';

  return (
    <>
      <SEOHead
        title={t('featuresPage.seoTitle')}
        description={t('featuresPage.seoDescription')}
        url="/features"
        type="website"
        jsonLd={{
          '@context': 'https://schema.org',
          '@type': 'SoftwareApplication',
          name: 'FilamentHub',
          url: absoluteLocalizedUrl('/features', locale),
          description: t('featuresPage.seoDescription'),
          applicationCategory: 'UtilitiesApplication',
          operatingSystem: 'Web, Windows, macOS, Linux',
          offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
          featureList: CAPABILITY_GROUPS.map((group) => t(`capabilities.groups.${group.id}.title`)),
        }}
      />
      <main className="relative z-10 mx-auto max-w-5xl px-4 py-8 sm:px-6">
        <Link
          to="/"
          className="mb-4 inline-flex items-center gap-2 text-purple-400 transition-colors hover:text-purple-300"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>{t('legalDocument.backHome')}</span>
        </Link>

        <header className="mb-4 flex items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-r from-purple-500 to-indigo-500 shadow-lg shadow-purple-500/25">
            <LayoutGrid className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-white">{t('featuresPage.title')}</h1>
        </header>
        <p className="max-w-3xl text-slate-300">{t('featuresPage.lead')}</p>

        <div className="mt-8 grid gap-4 lg:grid-cols-2">
          {CAPABILITY_GROUPS.map((group) => {
            const working = groupCapabilities(group.id, 'working');
            const progress = groupCapabilities(group.id, 'progress');
            return (
              <section
                key={group.id}
                aria-labelledby={`feature-${group.id}`}
                className="flex flex-col rounded-2xl border border-white/10 bg-white/[0.03] p-5"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 id={`feature-${group.id}`} className="text-xl font-semibold text-white">
                    {t(`capabilities.groups.${group.id}.title`)}
                  </h2>
                  <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${ACCESS_STYLES[group.access]}`}>
                    {t(`featuresPage.access.${group.access}`)}
                  </span>
                </div>
                <p className="mt-2 text-sm text-slate-300">{t(`capabilities.groups.${group.id}.text`)}</p>

                {working.length > 0 && (
                  <ul className="mt-4 space-y-2" aria-label={t('featuresPage.workingLabel')}>
                    {working.map((item) => (
                      <li key={item.id} className="flex gap-2.5 text-sm text-slate-300">
                        <CircleDot className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                        <span>{t(`capabilities.items.${item.id}`)}</span>
                      </li>
                    ))}
                  </ul>
                )}

                {progress.length > 0 && (
                  <div className="mt-4">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                      {t('featuresPage.progressLabel')}
                    </h3>
                    <ul className="mt-2 space-y-2">
                      {progress.map((item) => (
                        <li key={item.id} className="flex gap-2.5 text-sm text-slate-400">
                          <CircleDot className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                          <span>{t(`capabilities.items.${item.id}`)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 pt-1">
                  <Link
                    to={group.link}
                    className="inline-flex items-center gap-2 text-sm font-semibold text-purple-300 transition-colors hover:text-purple-200"
                  >
                    {t(`capabilities.groups.${group.id}.action`)}
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                  {group.demo && !user && (
                    <Link
                      to={group.demo}
                      className="inline-flex items-center gap-2 text-sm font-semibold text-cyan-300 transition-colors hover:text-cyan-200"
                    >
                      <Eye className="h-4 w-4" />
                      {t('demo.open')}
                    </Link>
                  )}
                </div>
              </section>
            );
          })}
        </div>

        <section className="mt-8 flex flex-col gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-xl font-semibold text-white">{t('featuresPage.aboutTitle')}</h2>
            <p className="mt-1 text-sm text-slate-300">{t('featuresPage.aboutText')}</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              to="/about"
              className="inline-flex items-center gap-2 rounded-xl border border-white/20 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-white/10"
            >
              {t('featuresPage.aboutAction')}
            </Link>
            {!user && (
              <Link
                to="/?auth=login"
                title={t('featuresPage.accountTitle')}
                className="inline-flex items-center gap-2 rounded-xl bg-purple-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-purple-500"
              >
                {t('featuresPage.accountAction')}
              </Link>
            )}
          </div>
        </section>
      </main>
    </>
  );
};
