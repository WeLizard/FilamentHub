import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Boxes,
  Calculator,
  Factory,
  PackageSearch,
  PlugZap,
  QrCode,
  Sparkles,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { SEOHead } from '../components/SEOHead';

type FeatureCard = {
  icon: keyof typeof ICONS;
  title: string;
  text: string;
  action: string;
  to: string;
};

type AudienceFlow = {
  title: string;
  text: string;
};

const ICONS = {
  catalog: PackageSearch,
  preset: Boxes,
  spool: QrCode,
  integration: PlugZap,
  calculation: Calculator,
  brand: Factory,
} as const;

export const FeaturesPage = () => {
  const { t } = useTranslation();
  const cardValues = t('featuresPage.cards', { returnObjects: true });
  const flowValues = t('featuresPage.flows', { returnObjects: true });
  const cards = Array.isArray(cardValues) ? cardValues as FeatureCard[] : [];
  const flows = Array.isArray(flowValues) ? flowValues as AudienceFlow[] : [];

  return (
    <>
      <SEOHead
        title={t('featuresPage.seoTitle')}
        description={t('featuresPage.seoDescription')}
        url="/features"
        type="website"
        jsonLd={{
          '@context': 'https://schema.org',
          '@type': 'WebPage',
          name: t('featuresPage.seoTitle'),
          description: t('featuresPage.seoDescription'),
        }}
      />

      <main className="relative z-10 mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:py-12">
        <Link
          to="/"
          className="mb-6 inline-flex items-center gap-2 text-sm text-purple-300 transition-colors hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>{t('legalDocument.backHome')}</span>
        </Link>

        <section className="overflow-hidden rounded-[2rem] border border-cyan-300/20 bg-slate-950/55 shadow-2xl shadow-purple-950/30 backdrop-blur-xl">
          <div className="relative px-6 py-10 sm:px-10 sm:py-14 lg:px-14">
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(34,211,238,0.15),transparent_34%),radial-gradient(circle_at_85%_15%,rgba(168,85,247,0.2),transparent_38%)]" />
            <div className="relative max-w-4xl">
              <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-cyan-300/30 bg-cyan-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">
                <Sparkles className="h-3.5 w-3.5" />
                {t('featuresPage.eyebrow')}
              </div>
              <h1 className="max-w-3xl text-4xl font-black leading-tight text-white sm:text-5xl lg:text-6xl">
                {t('featuresPage.title')}
              </h1>
              <p className="mt-6 max-w-3xl text-base leading-7 text-slate-300 sm:text-lg">
                {t('featuresPage.subtitle')}
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link
                  to="/"
                  className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-purple-500 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-cyan-950/25 transition-transform hover:-translate-y-0.5"
                >
                  {t('featuresPage.primaryAction')}
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <Link
                  to="/wiki"
                  className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/[0.06] px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-white/10"
                >
                  <BookOpen className="h-4 w-4 text-cyan-300" />
                  {t('featuresPage.secondaryAction')}
                </Link>
              </div>
            </div>
          </div>

          <div className="border-t border-white/10 bg-white/[0.035] px-6 py-6 sm:px-10 lg:px-14">
            <h2 className="text-lg font-semibold text-white">{t('featuresPage.principleTitle')}</h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-300">
              {t('featuresPage.principleText')}
            </p>
          </div>
        </section>

        <section className="mt-12">
          <h2 className="text-2xl font-bold text-white sm:text-3xl">{t('featuresPage.cardsTitle')}</h2>
          <p className="mt-2 text-slate-400">{t('featuresPage.cardsSubtitle')}</p>

          <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {cards.map((card) => {
              const Icon = ICONS[card.icon] ?? Boxes;
              return (
                <article
                  key={card.title}
                  className="group flex min-h-64 flex-col rounded-2xl border border-white/10 bg-slate-950/45 p-6 transition-all hover:-translate-y-1 hover:border-cyan-300/25 hover:bg-slate-950/60"
                >
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-cyan-300/20 bg-gradient-to-br from-cyan-500/20 to-purple-500/20 text-cyan-200">
                    <Icon className="h-5 w-5" />
                  </div>
                  <h3 className="mt-5 text-xl font-semibold text-white">{card.title}</h3>
                  <p className="mt-3 flex-1 text-sm leading-6 text-slate-300">{card.text}</p>
                  <Link
                    to={card.to}
                    className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-cyan-300 transition-colors group-hover:text-cyan-200"
                  >
                    {card.action}
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </article>
              );
            })}
          </div>
        </section>

        <section className="mt-12 rounded-[1.75rem] border border-white/10 bg-white/[0.035] p-6 sm:p-8">
          <h2 className="text-2xl font-bold text-white">{t('featuresPage.flowsTitle')}</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {flows.map((flow, index) => (
              <div key={flow.title} className="rounded-2xl border border-white/10 bg-slate-950/35 p-5">
                <div className="text-xs font-semibold tracking-[0.18em] text-purple-300">
                  {String(index + 1).padStart(2, '0')}
                </div>
                <h3 className="mt-3 text-lg font-semibold text-white">{flow.title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-300">{flow.text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-8 flex flex-col gap-5 rounded-[1.75rem] border border-purple-300/20 bg-gradient-to-r from-purple-950/55 to-cyan-950/35 p-6 sm:flex-row sm:items-center sm:justify-between sm:p-8">
          <div className="max-w-3xl">
            <h2 className="text-xl font-bold text-white">{t('featuresPage.guideTitle')}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-300">{t('featuresPage.guideText')}</p>
          </div>
          <Link
            to="/wiki"
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-cyan-100"
          >
            <BookOpen className="h-4 w-4" />
            {t('featuresPage.guideAction')}
          </Link>
        </section>
      </main>
    </>
  );
};
