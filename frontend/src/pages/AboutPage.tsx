import { ArrowLeft, ChevronDown, CircleDot, Download, Heart, Info } from 'lucide-react';
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

const LOGO_VARIANTS = [
  { key: 'light', svg: '/brand/logo-light.svg', png: '/brand/logo-light.png', preview: 'bg-white' },
  { key: 'dark', svg: '/logo.svg', png: '/brand/logo-dark.png', preview: 'bg-slate-950' },
] as const;

const BRAND_COLORS = [
  { name: 'purple', hex: '#7C3AED', rgb: '124, 58, 237' },
  { name: 'deepPurple', hex: '#3B0764', rgb: '59, 7, 100' },
  { name: 'white', hex: '#FFFFFF', rgb: '255, 255, 255' },
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

          <details id="brand-resources" className="group mt-10 rounded-2xl border border-white/10 bg-white/[0.03]">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 rounded-2xl p-5 marker:hidden focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-purple-400 [&::-webkit-details-marker]:hidden">
              <span>
                <span className="block text-xl font-semibold text-white">{t('aboutPage.brand.title')}</span>
                <span className="mt-1 block text-sm text-slate-400">{t('aboutPage.brand.description')}</span>
              </span>
              <ChevronDown aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-400 transition-transform group-open:rotate-180" />
            </summary>

            <div className="space-y-7 border-t border-white/10 p-5">
              <section aria-labelledby="brand-logo-title">
                <h3 id="brand-logo-title" className="text-lg font-semibold text-white">{t('aboutPage.brand.logoTitle')}</h3>
                <p className="mt-1 text-sm text-slate-400">{t('aboutPage.brand.logoNote')}</p>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  {LOGO_VARIANTS.map(({ key, svg, png, preview }) => (
                    <div key={key} className="overflow-hidden rounded-xl border border-white/10 bg-white/[0.03]">
                      <div className={`flex h-36 items-center justify-center ${preview}`}>
                        <img src={svg} alt={t(`aboutPage.brand.${key}Alt`)} className="h-24 w-32 object-contain" loading="lazy" />
                      </div>
                      <div className="p-4">
                        <p className="text-sm font-medium text-white">{t(`aboutPage.brand.${key}Label`)}</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <a href={svg} download className="inline-flex items-center gap-1.5 rounded-lg border border-white/20 px-3 py-2 text-sm text-slate-200 transition hover:bg-white/10"><Download className="h-4 w-4" />SVG</a>
                          <a href={png} download className="inline-flex items-center gap-1.5 rounded-lg border border-white/20 px-3 py-2 text-sm text-slate-200 transition hover:bg-white/10"><Download className="h-4 w-4" />PNG</a>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-sm text-slate-400">{t('aboutPage.brand.iconNote')} <a href="/favicon.svg" download className="text-purple-300 underline underline-offset-2 hover:text-purple-200">SVG</a> · <a href="/brand/icon.png" download className="text-purple-300 underline underline-offset-2 hover:text-purple-200">PNG</a></p>
              </section>

              <section aria-labelledby="brand-colors-title">
                <h3 id="brand-colors-title" className="text-lg font-semibold text-white">{t('aboutPage.brand.colorsTitle')}</h3>
                <div className="mt-3 grid gap-3 sm:grid-cols-3">
                  {BRAND_COLORS.map(({ name, hex, rgb }) => (
                    <div key={name} className="flex items-center gap-3 rounded-xl border border-white/10 p-3">
                      <span className="h-10 w-10 shrink-0 rounded-lg border border-white/20" style={{ backgroundColor: hex }} aria-hidden="true" />
                      <span className="min-w-0 text-sm"><span className="block font-medium text-white">{t(`aboutPage.brand.colors.${name}`)}</span><span className="block font-mono text-slate-300">{hex}</span><span className="block text-xs text-slate-500">RGB {rgb}</span></span>
                    </div>
                  ))}
                </div>
              </section>

              <section aria-labelledby="brand-guidelines-title">
                <h3 id="brand-guidelines-title" className="text-lg font-semibold text-white">{t('aboutPage.brand.guidelinesTitle')}</h3>
                <div className="mt-3 grid gap-4 text-sm text-slate-300 sm:grid-cols-2">
                  {(['please', 'dont'] as const).map((key) => (
                    <div key={key}>
                      <h4 className="font-medium text-white">{t(`aboutPage.brand.${key}Title`)}</h4>
                      <ul className="mt-2 list-disc space-y-1 pl-5">
                        {(t(`aboutPage.brand.${key}Items`, { returnObjects: true }) as string[]).map((item) => <li key={item}>{item}</li>)}
                      </ul>
                    </div>
                  ))}
                </div>
              </section>

              <a href="/brand/filamenthub-brand-pack.zip" download className="inline-flex items-center gap-2 rounded-xl bg-purple-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-purple-500">
                <Download className="h-4 w-4" />{t('aboutPage.brand.downloadPack')}
              </a>
            </div>
          </details>

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
