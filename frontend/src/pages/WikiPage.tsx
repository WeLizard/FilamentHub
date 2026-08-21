/** Главная страница Wiki - каталог знаний о 3D печати */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowRight,
  BookOpen,
  Boxes,
  Calculator,
  Check,
  ChevronRight,
  Clock,
  Compass,
  Eye,
  FilePenLine,
  Files,
  Factory,
  LibraryBig,
  Loader2,
  PackageOpen,
  QrCode,
  Route,
  Search,
  SearchCheck,
  ShieldCheck,
  SlidersHorizontal,
  Settings,
  Store,
  TrendingUp,
  X,
} from 'lucide-react';
import { wikiAPI } from '../api/client';
import { SEOHead } from '../components/SEOHead';
import { WikiAuthoringModal, WikiPeerReviewModal } from '../components/wiki';
import { plainWikiSummary } from '../components/wiki/wikiMarkdown';
import { toast } from '../components/Toast';
import { useAuth } from '../contexts/AuthContext';
import { WikiCategoryIcon } from '../components/wiki/WikiCategoryIcon';
import { Printer3DIcon } from '../components/icons/Printer3DIcon';
import {
  getCompletedWikiGuideIds,
  mergeCompletedWikiGuideIds,
  WIKI_GUIDE_PROGRESS_EVENT,
} from '../components/wiki/wikiGuideProgress';
import type { WikiArticleSummary, WikiLanguage, WikiRevision } from '../types/api';

export function WikiPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<WikiArticleSummary[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [authoringRevision, setAuthoringRevision] = useState<WikiRevision | 'new' | null>(null);
  const [reviewRevision, setReviewRevision] = useState<WikiRevision | null>(null);
  const [completedGuideIds, setCompletedGuideIds] = useState(() => getCompletedWikiGuideIds());
  const [activeUserJourneyHint, setActiveUserJourneyHint] = useState<string | null>(null);
  const [activeManufacturerJourneyHint, setActiveManufacturerJourneyHint] = useState<string | null>(null);
  const languageCode = i18n.resolvedLanguage?.split('-')[0];
  const currentLanguage: WikiLanguage = languageCode === 'ru' || languageCode === 'zh' ? languageCode : 'en';
  const guideJourneySteps = [
    { key: 'catalog', icon: PackageOpen, contentKey: 'catalog-material', progressId: 'user:catalog' },
    { key: 'slicer', icon: SlidersHorizontal, contentKey: 'orca-preset-guide', progressId: 'user:slicer' },
    { key: 'shelf', icon: Store, contentKey: 'spool-on-shelf', progressId: 'user:shelf' },
    { key: 'spools', icon: Boxes, contentKey: 'my-filaments-guide', progressId: 'user:spools' },
    { key: 'printer', icon: Printer3DIcon, contentKey: 'printer-feed-guide', progressId: 'user:printer' },
    { key: 'production', icon: Calculator, contentKey: 'production-calculation-guide', progressId: 'user:production' },
  ];
  const manufacturerJourneySteps = [
    { key: 'representation', icon: ShieldCheck, contentKey: 'brand-representation-guide', progressId: 'brand:representation' },
    { key: 'profile', icon: Factory, contentKey: 'brand-profile-guide', progressId: 'brand:profile' },
    { key: 'materials', icon: PackageOpen, contentKey: 'brand-materials-guide', progressId: 'brand:materials' },
    { key: 'presets', icon: Settings, contentKey: 'brand-official-presets-guide', progressId: 'brand:presets' },
    { key: 'qr', icon: QrCode, contentKey: 'brand-qr-guide', progressId: 'brand:qr' },
    { key: 'insights', icon: TrendingUp, contentKey: 'brand-insights-guide', progressId: 'brand:insights' },
  ];

  useEffect(() => {
    const refreshProgress = () => setCompletedGuideIds(getCompletedWikiGuideIds());
    window.addEventListener('storage', refreshProgress);
    window.addEventListener(WIKI_GUIDE_PROGRESS_EVENT, refreshProgress);
    return () => {
      window.removeEventListener('storage', refreshProgress);
      window.removeEventListener(WIKI_GUIDE_PROGRESS_EVENT, refreshProgress);
    };
  }, []);

  useEffect(() => {
    if (!user) return;
    let active = true;
    const syncProgress = async () => {
      try {
        const localGuideIds = [...getCompletedWikiGuideIds()];
        const response = localGuideIds.length > 0
          ? await wikiAPI.mergeGuideProgress(localGuideIds)
          : await wikiAPI.getGuideProgress();
        if (active) setCompletedGuideIds(mergeCompletedWikiGuideIds(response.guide_ids));
      } catch {
        // Progress is non-blocking; the local copy remains available offline.
      }
    };
    void syncProgress();
    return () => { active = false; };
  }, [user]);

  const { data: ownRevisions } = useQuery({
    queryKey: ['wiki-own-revisions', user?.id],
    queryFn: () => wikiAPI.listOwnRevisions({ page: 1, page_size: 6 }),
    enabled: Boolean(user),
    staleTime: 30_000,
  });

  const { data: reviewableRevisions } = useQuery({
    queryKey: ['wiki-reviewable-revisions', user?.id],
    queryFn: () => wikiAPI.listReviewableRevisions({ page: 1, page_size: 4 }),
    enabled: Boolean(user),
    staleTime: 30_000,
  });

  const retryRevision = useMutation({
    mutationFn: (revisionId: number) => wikiAPI.retryRevision(revisionId),
    onSuccess: (revision) => {
      queryClient.invalidateQueries({ queryKey: ['wiki-own-revisions'] });
      setAuthoringRevision(revision);
    },
    onError: () => toast.error(t('wikiAuthoring.retryError')),
  });

  const wikiDataQuery = useQuery({
    queryKey: ['wiki-home', currentLanguage],
    queryFn: async () => {
      const [categoriesData, guidesData, articlesData] = await Promise.all([
        wikiAPI.listCategories({ page: 1, page_size: 50, space: 'knowledge', language: currentLanguage }),
        wikiAPI.listArticles({ page: 1, page_size: 40, published_only: true, space: 'guides', language: currentLanguage }),
        wikiAPI.listArticles({ page: 1, page_size: 12, published_only: true, space: 'knowledge', language: currentLanguage }),
      ]);
      const sortedByViews = [...articlesData.items].sort((a, b) => b.views - a.views);
      const sortedByDate = [...articlesData.items].sort((a, b) => 
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      return {
        categories: categoriesData.items,
        guideArticles: guidesData.items,
        popularArticles: sortedByViews.slice(0, 6),
        recentArticles: sortedByDate.slice(0, 6),
      };
    },
    staleTime: 60_000,
  });

  const categories = wikiDataQuery.data?.categories ?? [];
  const guideArticles = wikiDataQuery.data?.guideArticles ?? [];
  const popularArticles = wikiDataQuery.data?.popularArticles ?? [];
  const recentArticles = wikiDataQuery.data?.recentArticles ?? [];
  const mainGuide = guideArticles.find((article) => article.content_key === 'filamenthub-workflow-overview')
    ?? guideArticles.find((article) => article.content_key === 'from-spool-to-print')
    ?? guideArticles[0];
  const journeyContentKeys = new Set(guideJourneySteps.map(({ contentKey }) => contentKey));
  const manufacturerContentKeys = new Set(manufacturerJourneySteps.map(({ contentKey }) => contentKey));
  const additionalGuides = guideArticles
    .filter((article) => (
      article.id !== mainGuide?.id
      && !journeyContentKeys.has(article.content_key)
      && !manufacturerContentKeys.has(article.content_key)
    ))
    .slice(0, 3);
  const visiblePopularArticles = popularArticles.slice(0, 4);
  const visibleRecentArticles = recentArticles.slice(0, 5);

  const findJourneyGuide = (contentKey: string) => (
    guideArticles.find((article) => article.content_key === contentKey)
  );

  const openGuide = (contentKey: string, progressId: string) => {
    const guide = findJourneyGuide(contentKey);
    if (!guide) return;
    navigate(`/wiki/articles/${guide.slug}?start=1&journey=${encodeURIComponent(progressId)}`);
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim().length < 2) return;

    try {
      setIsSearching(true);
      const response = await wikiAPI.searchArticles(searchQuery, { language: currentLanguage });
      setSearchResults(response.items);
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setIsSearching(false);
    }
  };

  const clearSearch = () => {
    setSearchQuery('');
    setSearchResults(null);
  };

  if (wikiDataQuery.isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 text-purple-500 animate-spin" />
      </div>
    );
  }

  if (wikiDataQuery.isError) {
    return (
      <div className="text-center py-12">
        <p className="text-red-400">{t('wikiPage.errorLoadFailed')}</p>
        <button
          onClick={() => void wikiDataQuery.refetch()}
          className="mt-4 px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
        >
          {t('wikiPage.retry')}
        </button>
      </div>
    );
  }

  return (
    <>
      <SEOHead
        title={t('wikiPage.seoTitle')}
        description={t('wikiPage.seoDescription')}
        keywords={t('wikiPage.seoKeywords')}
        url="/wiki"
        type="website"
        allowAI={true}
      />
      <div className="mx-auto max-w-7xl px-4 py-6 md:px-6 md:py-9">
      <header className="mb-7 grid items-center gap-5 border-b border-white/10 pb-7 lg:grid-cols-[minmax(0,0.8fr)_minmax(420px,1.2fr)]">
        <div className="flex min-w-0 items-center gap-4">
          <div className="flex h-13 w-13 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-500 shadow-lg shadow-blue-500/25 md:h-15 md:w-15">
            <BookOpen className="h-7 w-7 text-white md:h-8 md:w-8" />
          </div>
          <div className="min-w-0">
            <h1 className="text-3xl font-bold tracking-tight text-white md:text-4xl">{t('wikiPage.title')}</h1>
            <p className="mt-1.5 max-w-xl text-sm leading-6 text-slate-400 md:text-base">{t('wikiPage.subtitle')}</p>
          </div>
        </div>

        <form onSubmit={handleSearch} className="w-full">
          <div className="relative">
          <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
          <input
            type="text"
            placeholder={t('wikiPage.searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-2xl border border-white/15 bg-white/[0.075] py-4 pl-12 pr-12 text-white shadow-lg shadow-purple-950/10 outline-none transition placeholder:text-slate-500 focus:border-blue-400/60 focus:bg-white/[0.1] focus:ring-2 focus:ring-blue-500/20"
            aria-label={t('wikiPage.searchPlaceholder')}
          />
          {searchQuery && (
            <button
              type="button"
              onClick={clearSearch}
              className="absolute right-4 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>
        </form>
      </header>

      {/* Search Results */}
      {isSearching && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
        </div>
      )}

      {searchResults !== null && !isSearching && (
        <div className="mb-12">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold text-white flex items-center gap-2">
              <Search className="w-6 h-6 text-blue-400" />
              {t('wikiPage.searchResults', { count: searchResults.length })}
            </h2>
            <button
              onClick={clearSearch}
              className="text-sm text-gray-400 hover:text-white transition-colors"
            >
              {t('wikiPage.clearSearch')}
            </button>
          </div>

          {searchResults.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {searchResults.map((article) => (
                <button
                  key={article.id}
                  onClick={() => navigate(`/wiki/articles/${article.slug}`)}
                  className="group glass-panel border border-white/20 rounded-xl p-5 hover:bg-white/15 transition-all text-left"
                >
                  <div className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-white/[0.07] px-2.5 py-1 text-[11px] font-medium text-slate-400">
                    {article.space_key === 'guides' ? <Compass className="h-3 w-3 text-cyan-300" /> : <LibraryBig className="h-3 w-3 text-purple-300" />}
                    {article.space_key === 'guides' ? t('wikiPage.guideBadge') : t('wikiPage.knowledgeBadge')}
                  </div>
                  <h3 className="text-base font-semibold text-white mb-2 group-hover:text-blue-300 transition-colors line-clamp-2">
                    {article.title}
                  </h3>
                  <p className="text-sm text-gray-300 mb-3 line-clamp-2">{plainWikiSummary(article.summary)}</p>
                  <div className="flex items-center justify-between text-xs text-gray-400">
                    <div className="flex items-center gap-1">
                      <Eye className="w-3.5 h-3.5" />
                      <span>{article.views}</span>
                    </div>
                    {article.tags && article.tags.length > 0 && (
                      <div className="flex gap-1">
                        {article.tags.slice(0, 2).map((tag) => (
                          <span key={tag} className="px-1.5 py-0.5 bg-white/10 rounded text-gray-400">
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 glass-panel-subtle rounded-xl border border-white/10">
              <Search className="w-10 h-10 text-gray-500 mx-auto mb-3" />
              <p className="text-gray-400">{t('wikiPage.noResults')}</p>
            </div>
          )}
        </div>
      )}

      {/* Main content (hidden during search) */}
      {searchResults === null && (<>
      <div className={`mb-12 grid items-stretch gap-5 ${user ? 'lg:grid-cols-[minmax(0,1.8fr)_minmax(310px,0.8fr)]' : ''}`}>
        <section className="relative overflow-hidden rounded-3xl border border-cyan-300/15 bg-gradient-to-br from-blue-500/15 via-cyan-500/[0.08] to-purple-500/10 p-5 shadow-2xl shadow-blue-950/20 md:p-7">
          <span className="pointer-events-none absolute -right-16 -top-20 h-64 w-64 rounded-full bg-cyan-300/[0.07] blur-3xl" />
          <div className="relative">
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-300/15 bg-cyan-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.15em] text-cyan-200">
              <ShieldCheck className="h-3.5 w-3.5" />{t('wikiPage.officialGuides')}
            </div>
            <h2 className="mt-3 flex items-center gap-3 text-2xl font-bold text-white md:text-3xl"><Compass className="h-7 w-7 text-cyan-300" />{t('wikiPage.guidesTitle')}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">{t('wikiPage.guidesDescription')}</p>
          </div>

          <div className="relative mt-6 rounded-2xl border border-white/10 bg-[#09172b]/50 p-3 md:p-4">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-2 px-1">
              <div>
                <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
                  <Route className="h-4 w-4 text-cyan-300" />
                  {t('wikiPage.chooseTask')}
                </h3>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  {activeUserJourneyHint
                    ? t(`wikiPage.journeyDescriptions.${activeUserJourneyHint}`)
                    : t('wikiPage.chooseTaskHint')}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-x-1 gap-y-4 md:grid-cols-3 xl:grid-cols-6 xl:gap-0">
              {guideJourneySteps.map(({ key, icon: StepIcon, contentKey, progressId }, index) => {
                const guide = findJourneyGuide(contentKey);
                const isCompleted = completedGuideIds.has(progressId)
                  || Boolean(guide && completedGuideIds.has(`article:${guide.content_key}`));
                return (
                  <div key={key} className="relative min-w-0">
                    <button
                      type="button"
                      disabled={!guide}
                      onClick={() => openGuide(contentKey, progressId)}
                      onMouseEnter={() => setActiveUserJourneyHint(key)}
                      onMouseLeave={() => setActiveUserJourneyHint(null)}
                      onFocus={() => setActiveUserJourneyHint(key)}
                      onBlur={() => setActiveUserJourneyHint(null)}
                      className="group relative z-10 flex h-full w-full min-w-0 flex-col items-center gap-2 rounded-xl px-2 py-1.5 text-center outline-none transition focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cyan-300/35 disabled:cursor-not-allowed disabled:opacity-45"
                    >
                      <span aria-hidden="true" className="pointer-events-none absolute bottom-0 left-1/2 h-px w-0 -translate-x-1/2 bg-gradient-to-r from-transparent via-cyan-300 to-transparent opacity-0 shadow-[0_2px_12px_rgba(34,211,238,0.7)] transition-all duration-200 group-hover:w-2/3 group-hover:opacity-100 group-focus-visible:w-2/3 group-focus-visible:opacity-100" />
                      <span className="relative flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-400/10 text-cyan-200 ring-1 ring-cyan-300/15 transition group-hover:bg-cyan-400/15 group-hover:ring-cyan-300/30">
                        <StepIcon className="h-4 w-4" />
                        {isCompleted && (
                          <span className="absolute -right-1.5 -top-1.5 flex h-[18px] w-[18px] items-center justify-center rounded-full border border-emerald-300/45 bg-emerald-950 text-emerald-200 shadow-sm shadow-emerald-950/50" title={t('wikiPage.guideCompleted')} aria-label={t('wikiPage.guideCompleted')}>
                            <Check className="h-2.5 w-2.5" />
                          </span>
                        )}
                      </span>
                      <span className="line-clamp-2 text-xs font-medium leading-4 text-slate-400 transition group-hover:text-white">{t(`wikiPage.journey.${key}`)}</span>
                    </button>
                    {index < guideJourneySteps.length - 1 && (
                      <span aria-hidden="true" className="pointer-events-none absolute -right-1.5 top-4 z-30 hidden items-center justify-center text-cyan-300/35 xl:flex">
                        <ArrowRight className="h-4 w-4" />
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="relative mt-5 rounded-2xl border border-purple-300/15 bg-[#160f2d]/55 p-3 md:p-4">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-2 px-1">
              <div>
                <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
                  <Factory className="h-4 w-4 text-purple-200" />
                  {t('wikiPage.manufacturerJourneyTitle')}
                </h3>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  {activeManufacturerJourneyHint
                    ? t(`wikiPage.manufacturerJourneyDescriptions.${activeManufacturerJourneyHint}`)
                    : t('wikiPage.manufacturerJourneyHint')}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-x-1 gap-y-4 md:grid-cols-3 xl:grid-cols-6 xl:gap-0">
              {manufacturerJourneySteps.map(({ key, icon: StepIcon, contentKey, progressId }, index) => {
                const guide = findJourneyGuide(contentKey);
                const isCompleted = completedGuideIds.has(progressId)
                  || Boolean(guide && completedGuideIds.has(`article:${guide.content_key}`));
                return (
                  <div key={key} className="relative min-w-0">
                    <button
                      type="button"
                      disabled={!guide}
                      onClick={() => openGuide(contentKey, progressId)}
                      onMouseEnter={() => setActiveManufacturerJourneyHint(key)}
                      onMouseLeave={() => setActiveManufacturerJourneyHint(null)}
                      onFocus={() => setActiveManufacturerJourneyHint(key)}
                      onBlur={() => setActiveManufacturerJourneyHint(null)}
                      className="group relative z-10 flex h-full w-full min-w-0 flex-col items-center gap-2 rounded-xl px-2 py-1.5 text-center outline-none transition focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-purple-300/35 disabled:cursor-not-allowed disabled:opacity-45"
                    >
                      <span aria-hidden="true" className="pointer-events-none absolute bottom-0 left-1/2 h-px w-0 -translate-x-1/2 bg-gradient-to-r from-transparent via-purple-300 to-transparent opacity-0 shadow-[0_2px_12px_rgba(192,132,252,0.7)] transition-all duration-200 group-hover:w-2/3 group-hover:opacity-100 group-focus-visible:w-2/3 group-focus-visible:opacity-100" />
                      <span className="relative flex h-10 w-10 items-center justify-center rounded-lg bg-purple-400/10 text-purple-100 ring-1 ring-purple-300/15 transition group-hover:bg-purple-400/15 group-hover:ring-purple-300/30">
                        <StepIcon className="h-4 w-4" />
                        {isCompleted && (
                          <span className="absolute -right-1.5 -top-1.5 flex h-[18px] w-[18px] items-center justify-center rounded-full border border-emerald-300/45 bg-emerald-950 text-emerald-200 shadow-sm shadow-emerald-950/50" title={t('wikiPage.guideCompleted')} aria-label={t('wikiPage.guideCompleted')}>
                            <Check className="h-2.5 w-2.5" />
                          </span>
                        )}
                      </span>
                      <span className="line-clamp-2 text-xs font-medium leading-4 text-slate-400 transition group-hover:text-white">{t(`wikiPage.manufacturerJourney.${key}`)}</span>
                    </button>
                    {index < manufacturerJourneySteps.length - 1 && (
                      <span aria-hidden="true" className="pointer-events-none absolute -right-1.5 top-4 z-30 hidden items-center justify-center text-purple-200/40 xl:flex">
                        <ArrowRight className="h-4 w-4" />
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {additionalGuides.length > 0 && (
            <div className="relative mt-4 grid gap-2 md:grid-cols-2">
              {additionalGuides.map((article) => (
                <button key={article.id} type="button" onClick={() => navigate(`/wiki/articles/${article.slug}`)} className="group flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.035] px-4 py-3 text-left transition hover:border-cyan-300/20 hover:bg-white/[0.065]">
                  <span className="line-clamp-2 text-sm font-medium text-slate-300 group-hover:text-white">{article.title}</span>
                  <ChevronRight className="h-4 w-4 shrink-0 text-cyan-300/60 transition-transform group-hover:translate-x-0.5" />
                </button>
              ))}
            </div>
          )}
        </section>

        {user && (
          <aside className="flex min-h-full flex-col overflow-hidden rounded-3xl border border-purple-300/15 bg-gradient-to-b from-purple-500/10 to-[#111827]/80 p-5 shadow-xl shadow-purple-950/15">
            <div className="flex items-start justify-between gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-purple-500/15 text-purple-200 ring-1 ring-purple-400/20"><Files className="h-5 w-5" /></span>
              {ownRevisions && <span className="rounded-full border border-white/10 bg-white/[0.05] px-2.5 py-1 text-xs font-medium tabular-nums text-slate-400">{ownRevisions.total}</span>}
            </div>
            <h2 className="mt-4 text-xl font-bold text-white">{t('wikiPage.workTitle')}</h2>
            <p className="mt-1 text-sm leading-6 text-slate-400">{t('wikiPage.workDescription')}</p>

            <div className="mt-5 space-y-2">
              {ownRevisions && ownRevisions.items.length > 0 ? ownRevisions.items.slice(0, 3).map((revision) => (
                <button key={revision.id} type="button" disabled={revision.status !== 'draft' && revision.status !== 'rejected'} onClick={() => revision.status === 'rejected' ? retryRevision.mutate(revision.id) : setAuthoringRevision(revision)} className="group w-full rounded-xl border border-white/10 bg-black/10 px-3.5 py-3 text-left transition hover:border-purple-300/25 hover:bg-white/[0.055] disabled:cursor-default disabled:hover:border-white/10">
                  <div className="truncate text-sm font-medium text-slate-200 group-hover:text-white">{revision.title}</div>
                  <div className="mt-1.5 flex items-center justify-between gap-2 text-xs text-slate-500"><span>v{revision.revision_number}</span><span className={revision.status === 'pending_review' ? 'text-amber-300' : revision.status === 'published' ? 'text-emerald-300' : revision.status === 'rejected' ? 'text-rose-300' : 'text-blue-300'}>{t(`wikiAuthoring.status.${revision.status}`)}</span></div>
                </button>
              )) : (
                <div className="rounded-xl border border-dashed border-white/10 px-4 py-5 text-sm leading-6 text-slate-500">{t('wikiPage.workEmpty')}</div>
              )}
            </div>

            {reviewableRevisions && reviewableRevisions.items.length > 0 && (
              <button type="button" onClick={() => setReviewRevision(reviewableRevisions.items[0])} className="mt-3 flex items-center justify-between gap-3 rounded-xl border border-cyan-300/10 bg-cyan-500/[0.04] px-3.5 py-3 text-left transition hover:border-cyan-300/25 hover:bg-cyan-500/[0.08]">
                <span className="min-w-0"><span className="block text-xs font-semibold uppercase tracking-wider text-cyan-300/70">{t('wikiPage.communityReview')}</span><span className="mt-1 block truncate text-sm text-slate-300">{reviewableRevisions.items[0].title}</span></span>
                <SearchCheck className="h-4 w-4 shrink-0 text-cyan-300" />
              </button>
            )}

            <div className="mt-auto grid gap-2 pt-5">
              <button type="button" onClick={() => navigate('/wiki/workspace')} className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/[0.05] px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:bg-white/10 hover:text-white"><Files className="h-4 w-4" />{t('wikiAuthoring.openWorkspace')}</button>
              <button type="button" onClick={() => setAuthoringRevision('new')} className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-500 to-purple-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-purple-950/30 transition hover:brightness-110"><FilePenLine className="h-4 w-4" />{t('wikiAuthoring.writeArticle')}</button>
            </div>
          </aside>
        )}
      </div>

      <section className="mb-12">
        <div className="mb-6 flex items-end justify-between gap-5">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-purple-500/15 text-purple-200 ring-1 ring-purple-400/20"><LibraryBig className="h-5 w-5" /></span>
            <div><div className="text-xs font-semibold uppercase tracking-[0.15em] text-purple-300/75">{t('wikiPage.categories')}</div><h2 className="mt-1 text-2xl font-bold text-white">{t('wikiPage.knowledgeTitle')}</h2><p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">{t('wikiPage.knowledgeDescription')}</p></div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {categories.map((category) => (
              <button
                key={category.id}
                onClick={() => navigate(`/wiki/${category.slug}`)}
                className="group relative flex aspect-[3/4] min-h-[250px] flex-col overflow-hidden rounded-l-md rounded-r-2xl border border-white/15 bg-gradient-to-br from-white/[0.11] to-white/[0.045] p-5 pl-7 text-left shadow-xl shadow-purple-950/15 transition hover:-translate-y-1 hover:border-cyan-300/30 hover:shadow-2xl hover:shadow-purple-950/30"
              >
                <span className="absolute inset-y-0 left-0 w-3 border-r border-white/10 bg-black/15 shadow-[3px_0_12px_rgba(0,0,0,0.18)]" />
                <div className="flex items-start justify-between">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 shadow-lg shadow-blue-950/30">
                    <WikiCategoryIcon name={category.icon} className="w-6 h-6 text-white" />
                  </div>
                  <ChevronRight className="h-5 w-5 text-slate-500 transition group-hover:translate-x-0.5 group-hover:text-cyan-200" />
                </div>
                <h3 className="mt-6 text-lg font-semibold leading-tight text-white">{t(`wikiAuthoring.categories.${category.slug}`, { defaultValue: category.name })}</h3>
                <p className="mt-3 line-clamp-4 text-sm leading-6 text-slate-400">{category.description}</p>
                <div className="mt-auto border-t border-white/10 pt-4 text-xs text-slate-500">
                  {category.articles_count} {t('wikiPage.articles')}
                </div>
              </button>
          ))}
        </div>
      </section>

      {(visiblePopularArticles.length > 0 || visibleRecentArticles.length > 0) && (
        <section className="mb-12 grid gap-6 lg:grid-cols-[minmax(0,1.45fr)_minmax(290px,0.65fr)]">
          {visiblePopularArticles.length > 0 && (
            <div>
              <div className="mb-5 flex items-start gap-3">
                <TrendingUp className="mt-0.5 h-6 w-6 shrink-0 text-yellow-400" />
                <div><h2 className="text-xl font-bold text-white md:text-2xl">{t('wikiPage.popularArticles')}</h2><p className="mt-1 text-sm text-slate-500">{t('wikiPage.popularDescription')}</p></div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                {visiblePopularArticles.map((article) => (
                  <button key={article.id} onClick={() => navigate(`/wiki/articles/${article.slug}`)} className="group relative overflow-hidden rounded-2xl border border-white/15 bg-white/[0.075] p-5 pl-7 text-left transition hover:-translate-y-0.5 hover:border-purple-300/25 hover:bg-white/[0.1]">
                    <span className="absolute inset-y-0 left-0 w-2 border-r border-white/10 bg-gradient-to-b from-purple-500/35 to-blue-500/15" />
                    <h3 className="line-clamp-2 text-base font-semibold text-white transition group-hover:text-purple-100">{article.title}</h3>
                    <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-400">{plainWikiSummary(article.summary)}</p>
                    <div className="mt-4 flex items-center justify-between gap-3 text-xs text-slate-500"><span className="flex items-center gap-1"><Eye className="h-3.5 w-3.5" />{article.views}</span>{article.author && <span className="truncate">{article.author}</span>}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {visibleRecentArticles.length > 0 && (
            <div className="rounded-3xl border border-white/10 bg-black/10 p-5">
              <div className="mb-4 flex items-start gap-3">
                <Clock className="mt-0.5 h-5 w-5 shrink-0 text-emerald-300" />
                <div><h2 className="text-lg font-bold text-white">{t('wikiPage.recentArticles')}</h2><p className="mt-1 text-xs leading-5 text-slate-500">{t('wikiPage.recentDescription')}</p></div>
              </div>
              <div className="divide-y divide-white/10">
                {visibleRecentArticles.map((article) => (
                  <button key={article.id} onClick={() => navigate(`/wiki/articles/${article.slug}`)} className="group flex w-full items-start justify-between gap-3 py-3 text-left first:pt-1 last:pb-1">
                    <span className="min-w-0"><span className="line-clamp-2 text-sm font-medium leading-5 text-slate-300 transition group-hover:text-emerald-100">{article.title}</span><span className="mt-1 block text-xs text-slate-600">{new Date(article.created_at).toLocaleDateString(i18n.resolvedLanguage)}</span></span>
                    <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-600 transition group-hover:translate-x-0.5 group-hover:text-emerald-300" />
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* Empty State */}
      {categories.length === 0 && popularArticles.length === 0 && guideArticles.length === 0 && (
        <div className="text-center py-12 glass-panel-subtle rounded-2xl border border-white/10">
          <BookOpen className="w-16 h-16 text-gray-400 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-white mb-2">{t('wikiPage.emptyTitle')}</h3>
          <p className="text-gray-400">
            {t('wikiPage.emptyDesc')}
          </p>
        </div>
      )}
      </>)}
      </div>
      {authoringRevision && (
        <WikiAuthoringModal
          categories={categories}
          revision={authoringRevision === 'new' ? null : authoringRevision}
          onClose={() => setAuthoringRevision(null)}
          onSaved={() => {
            queryClient.invalidateQueries({ queryKey: ['wiki-own-revisions'] });
          }}
        />
      )}
      {reviewRevision && <WikiPeerReviewModal revision={reviewRevision} onClose={() => setReviewRevision(null)} />}
    </>
  );
}

