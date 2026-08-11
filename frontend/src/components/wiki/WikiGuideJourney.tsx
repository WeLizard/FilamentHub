import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Compass,
  Play,
  Route,
} from 'lucide-react';

import type { WikiArticle } from '../../types/api';
import { ShareMenu } from '../ShareMenu';
import { WikiContentRenderer } from './WikiContentRenderer';
import {
  WikiGuideCalloutLegend,
  WikiGuideImageCanvas,
  WikiGuideImageViewer,
} from './WikiGuideImageViewer';
import { parseWikiGuide, type WikiGuideImage } from './wikiGuide';
import { markWikiGuideCompleted } from './wikiGuideProgress';

interface WikiGuideJourneyProps {
  article: WikiArticle;
  content: string;
  onBack: () => void;
}

export function WikiGuideJourney({ article, content, onBack }: WikiGuideJourneyProps) {
  const { t } = useTranslation();
  const guide = useMemo(() => parseWikiGuide(content), [content]);
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedStep = Number.parseInt(searchParams.get('step') ?? '', 10);
  const initialIndex = Number.isFinite(requestedStep)
    ? Math.min(Math.max(requestedStep, 0), Math.max(guide.steps.length - 1, 0))
    : 0;
  const [activeIndex, setActiveIndex] = useState(initialIndex);
  const [started, setStarted] = useState(searchParams.get('start') === '1' || searchParams.has('step'));
  const [overviewExpanded, setOverviewExpanded] = useState(false);
  const [viewerImage, setViewerImage] = useState<WikiGuideImage | null>(null);
  const [activeCallout, setActiveCallout] = useState<number | null>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const journeyId = searchParams.get('journey');

  useEffect(() => {
    setActiveIndex(initialIndex);
    setStarted(searchParams.get('start') === '1' || searchParams.has('step'));
    setOverviewExpanded(false);
    setViewerImage(null);
    setActiveCallout(null);
  }, [article.id]);

  if (guide.steps.length === 0) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-8 md:px-6 md:py-12">
        <WikiContentRenderer content={guide.intro} taskStorageKey={`wiki-guide-${article.slug}`} />
      </div>
    );
  }

  const activeStep = guide.steps[activeIndex];
  const isLastStep = activeIndex === guide.steps.length - 1;
  const progress = Math.round(((activeIndex + 1) / guide.steps.length) * 100);

  const selectStep = (index: number) => {
    setActiveIndex(index);
    setActiveCallout(null);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('step', String(index));
    nextParams.set('start', '1');
    setSearchParams(nextParams, { replace: true });
    window.requestAnimationFrame(() => {
      workspaceRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  const startGuide = () => {
    setStarted(true);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('step', String(activeIndex));
    nextParams.set('start', '1');
    setSearchParams(nextParams, { replace: true });
  };

  const finishGuide = () => {
    markWikiGuideCompleted(journeyId ?? `article:${article.slug}`);
    onBack();
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 md:px-6 md:py-10">
      <div className="mb-5 flex items-center justify-between gap-3">
        <button type="button" onClick={onBack} className="group inline-flex items-center gap-2 text-sm text-slate-300 transition hover:text-white">
          <ArrowLeft className="h-4 w-4 transition-transform group-hover:-translate-x-0.5" />
          {t('wikiArticlePage.back')}
        </button>
        <ShareMenu title={article.title} description={article.summary} />
      </div>

      {!started ? (
        <header className="relative overflow-hidden rounded-3xl border border-cyan-300/15 bg-gradient-to-br from-[#0b1c34] via-[#14213d] to-[#25133f] p-6 shadow-2xl shadow-blue-950/25 md:p-8">
          <span className="pointer-events-none absolute -right-20 -top-28 h-72 w-72 rounded-full bg-cyan-300/10 blur-3xl" />
          <span className="relative inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200">
            <Compass className="h-3.5 w-3.5" />
            {t('wikiPage.guideBadge')}
          </span>
          <div className="relative mt-4 grid gap-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
            <div>
              <h1 className="max-w-4xl text-3xl font-bold leading-tight text-white md:text-4xl">{article.title}</h1>
              <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-300 md:text-base">{article.summary}</p>
            </div>
            <div className="flex flex-col items-stretch gap-3 sm:min-w-64">
              <p className="text-xs font-medium text-slate-400">{t('wikiGuide.stepCount', { count: guide.steps.length })}</p>
              <button
                type="button"
                onClick={startGuide}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-500 to-cyan-500 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-950/30 transition hover:brightness-110"
              >
                <Play className="h-4 w-4 fill-current" />
                {t('wikiGuide.start')}
              </button>
            </div>
          </div>
        </header>
      ) : (
        <>
          <header className="rounded-2xl border border-cyan-300/15 bg-[#0b1729]/90 px-4 py-3 shadow-lg shadow-black/15 md:px-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.15em] text-cyan-300">
                  <Compass className="h-3.5 w-3.5" />
                  {t('wikiPage.guideBadge')}
                </div>
                <h1 className="mt-1 truncate text-lg font-semibold text-white md:text-xl">{article.title}</h1>
              </div>
              <div className="flex items-center gap-3 sm:min-w-80">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-3 text-xs text-slate-400">
                    <span>{t('wikiGuide.stepOf', { current: activeIndex + 1, total: guide.steps.length })}</span>
                    <span className="font-semibold tabular-nums text-cyan-200">{progress}%</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/10">
                    <div className="h-full rounded-full bg-gradient-to-r from-blue-400 to-cyan-300 transition-[width] duration-300" style={{ width: `${progress}%` }} />
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setOverviewExpanded((current) => !current)}
                  aria-expanded={overviewExpanded}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/[0.07] hover:text-white"
                >
                  {overviewExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  {overviewExpanded ? t('wikiGuide.hideOverview') : t('wikiGuide.showOverview')}
                </button>
              </div>
            </div>
            {overviewExpanded && (
              <div className="mt-3 border-t border-white/10 pt-3 text-sm leading-6 text-slate-400">
                {article.summary}
              </div>
            )}
          </header>

          <div ref={workspaceRef} id="wiki-guide-workspace" className="mt-5 grid scroll-mt-24 gap-5 lg:grid-cols-[270px_minmax(0,1fr)]">
            <nav aria-label={t('wikiGuide.steps')} className="overflow-hidden rounded-2xl border border-white/10 bg-[#0d1728]/80 p-2 lg:sticky lg:top-24 lg:self-start">
          <div className="mb-2 flex items-center gap-2 px-3 py-2 text-xs font-semibold uppercase tracking-[0.15em] text-slate-500">
            <Route className="h-4 w-4 text-cyan-300" />
            {t('wikiGuide.steps')}
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1 lg:block lg:space-y-1 lg:overflow-visible">
            {guide.steps.map((step, index) => {
              const isActive = index === activeIndex;
              const isCompleted = index < activeIndex;
              return (
                <button
                  key={step.id}
                  type="button"
                  onClick={() => selectStep(index)}
                  className={`flex min-w-56 items-start gap-3 rounded-xl px-3 py-3 text-left transition lg:min-w-0 lg:w-full ${isActive ? 'bg-cyan-400/10 text-white ring-1 ring-cyan-300/20' : 'text-slate-400 hover:bg-white/[0.045] hover:text-slate-200'}`}
                >
                  <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold ${isActive ? 'border-cyan-300/40 bg-cyan-300/15 text-cyan-100' : isCompleted ? 'border-emerald-300/30 bg-emerald-400/10 text-emerald-200' : 'border-white/10 bg-white/[0.03] text-slate-500'}`}>
                    {isCompleted ? <Check className="h-3.5 w-3.5" /> : index + 1}
                  </span>
                  <span className="line-clamp-3 text-sm font-medium leading-5">{step.title.replace(/^\d+[.)]\s*/, '')}</span>
                </button>
              );
            })}
          </div>
            </nav>

            <section className="overflow-hidden rounded-3xl border border-white/10 bg-[#0d1728]/75 shadow-xl shadow-black/20">
              {activeStep.image && (
                <figure className="border-b border-white/10 bg-[#07111f] p-3 md:p-5">
                  <WikiGuideImageCanvas image={activeStep.image} onOpen={() => setViewerImage(activeStep.image)} activeCallout={activeCallout} onActiveCalloutChange={setActiveCallout} />
                  <figcaption className="mt-2 px-1 text-xs leading-5 text-slate-500">
                    {activeStep.image.alt} · {t('wikiGuide.openImage')}
                  </figcaption>
                  <WikiGuideCalloutLegend image={activeStep.image} activeCallout={activeCallout} onActiveCalloutChange={setActiveCallout} />
                </figure>
              )}

              <div className="p-5 md:p-8">
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-300">{t('wikiGuide.stepOf', { current: activeIndex + 1, total: guide.steps.length })}</div>
            <h2 className="mt-2 text-2xl font-bold leading-tight text-white md:text-3xl">{activeStep.title.replace(/^\d+[.)]\s*/, '')}</h2>
            <div className="mt-5">
              <WikiContentRenderer content={activeStep.content} taskStorageKey={`wiki-guide-${article.slug}-${activeStep.id}`} />
            </div>

            <div className="mt-8 flex flex-col-reverse gap-3 border-t border-white/10 pt-5 sm:flex-row sm:items-center sm:justify-between">
              <button
                type="button"
                onClick={() => selectStep(Math.max(0, activeIndex - 1))}
                disabled={activeIndex === 0}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.035] px-4 py-2.5 text-sm font-medium text-slate-300 transition hover:bg-white/[0.07] hover:text-white disabled:cursor-not-allowed disabled:opacity-35"
              >
                <ChevronLeft className="h-4 w-4" />
                {t('wikiGuide.previous')}
              </button>
              <button
                type="button"
                onClick={() => isLastStep ? finishGuide() : selectStep(activeIndex + 1)}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-500 to-cyan-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-blue-950/30 transition hover:brightness-110"
              >
                {isLastStep ? t('wikiGuide.finish') : t('wikiGuide.next')}
                {isLastStep ? <ArrowRight className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </button>
            </div>
              </div>
            </section>
          </div>
        </>
      )}

      <WikiGuideImageViewer image={viewerImage} onClose={() => setViewerImage(null)} />
    </div>
  );
}
