/** Главная страница Wiki - каталог знаний о 3D печати */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, Search, TrendingUp, Clock, Eye, ChevronRight, Loader2, X, FilePenLine, Files, Compass, LibraryBig, ShieldCheck, SearchCheck } from 'lucide-react';
import { wikiAPI } from '../api/client';
import { SEOHead } from '../components/SEOHead';
import { WikiAuthoringModal, WikiPeerReviewModal } from '../components/wiki';
import { toast } from '../components/Toast';
import { useAuth } from '../contexts/AuthContext';
import type { WikiCategory, WikiArticleSummary, WikiLanguage, WikiRevision } from '../types/api';

// Маппинг названий иконок Lucide на компоненты
import * as LucideIcons from 'lucide-react';

export function WikiPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [categories, setCategories] = useState<WikiCategory[]>([]);
  const [guideArticles, setGuideArticles] = useState<WikiArticleSummary[]>([]);
  const [popularArticles, setPopularArticles] = useState<WikiArticleSummary[]>([]);
  const [recentArticles, setRecentArticles] = useState<WikiArticleSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<WikiArticleSummary[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [authoringRevision, setAuthoringRevision] = useState<WikiRevision | 'new' | null>(null);
  const [reviewRevision, setReviewRevision] = useState<WikiRevision | null>(null);
  const languageCode = i18n.resolvedLanguage?.split('-')[0];
  const currentLanguage: WikiLanguage = languageCode === 'ru' || languageCode === 'zh' ? languageCode : 'en';

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

  useEffect(() => {
    void loadData();
  }, [currentLanguage]);

  const loadData = async () => {
    try {
      setIsLoading(true);
      setError(null);

      let [categoriesData, guidesData, articlesData] = await Promise.all([
        wikiAPI.listCategories({ page: 1, page_size: 50, space: 'knowledge', language: currentLanguage }),
        wikiAPI.listArticles({ page: 1, page_size: 6, published_only: true, space: 'guides', language: currentLanguage }),
        wikiAPI.listArticles({ page: 1, page_size: 12, published_only: true, space: 'knowledge', language: currentLanguage }),
      ]);
      if (currentLanguage !== 'ru' && articlesData.total === 0) {
        [categoriesData, articlesData] = await Promise.all([
          wikiAPI.listCategories({ page: 1, page_size: 50, space: 'knowledge', language: 'ru' }),
          wikiAPI.listArticles({ page: 1, page_size: 12, published_only: true, space: 'knowledge', language: 'ru' }),
        ]);
      }
      if (currentLanguage !== 'ru' && guidesData.total === 0) {
        guidesData = await wikiAPI.listArticles({ page: 1, page_size: 6, published_only: true, space: 'guides', language: 'ru' });
      }
      setCategories(categoriesData.items);
      setGuideArticles(guidesData.items);
      
      // Сортируем по просмотрам локально
      const sortedByViews = [...articlesData.items].sort((a, b) => b.views - a.views);
      setPopularArticles(sortedByViews.slice(0, 6));

      // Сортируем по дате создания
      const sortedByDate = [...articlesData.items].sort((a, b) => 
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      setRecentArticles(sortedByDate.slice(0, 6));

    } catch (err: any) {
      console.error('Failed to load wiki data:', err);
      setError(t('wikiPage.errorLoadFailed'));
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim().length < 2) return;

    try {
      setIsSearching(true);
      let response = await wikiAPI.searchArticles(searchQuery, { language: currentLanguage });
      if (currentLanguage !== 'ru' && response.total === 0) {
        response = await wikiAPI.searchArticles(searchQuery, { language: 'ru' });
      }
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

  const getIconComponent = (iconName: string | null) => {
    if (!iconName) return BookOpen;
    
    // Преобразуем имя иконки в PascalCase если нужно
    const IconComponent = (LucideIcons as unknown as Record<string, LucideIcons.LucideIcon>)[iconName];
    return IconComponent || BookOpen;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 text-purple-500 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-400">{error}</p>
        <button
          onClick={loadData}
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
      <div className="max-w-6xl mx-auto px-4 md:px-6 py-6 md:py-12">
        {/* Header */}
      <div className="text-center mb-8 md:mb-12">
        <div className="flex items-center justify-center gap-3 mb-4">
          <div className="w-12 h-12 md:w-16 md:h-16 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-xl md:rounded-2xl flex items-center justify-center shadow-lg shadow-blue-500/25">
            <BookOpen className="w-6 h-6 md:w-8 md:h-8 text-white" />
          </div>
          <h1 className="text-3xl md:text-4xl font-bold text-white">{t('wikiPage.title')}</h1>
        </div>
        <p className="text-base md:text-xl text-gray-300 max-w-2xl mx-auto">
          {t('wikiPage.subtitle')}
        </p>
      </div>

      {user && (
        <section className="mb-8 overflow-hidden rounded-2xl border border-blue-400/15 bg-gradient-to-r from-blue-500/10 via-purple-500/10 to-white/[0.03] p-4 md:mb-10 md:p-5">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-500/15 text-blue-300 ring-1 ring-blue-400/20"><FilePenLine className="h-5 w-5" /></span>
              <div>
                <h2 className="font-semibold text-white">{t('wikiAuthoring.contributeTitle')}</h2>
                <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-400">{t('wikiAuthoring.contributeDescription')}</p>
              </div>
            </div>
            <button type="button" onClick={() => setAuthoringRevision('new')} className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-500 to-purple-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-purple-950/30 transition hover:brightness-110">
              <FilePenLine className="h-4 w-4" />{t('wikiAuthoring.writeArticle')}
            </button>
          </div>
          {ownRevisions && ownRevisions.items.length > 0 && (
            <div className="mt-4 border-t border-white/10 pt-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-500"><Files className="h-3.5 w-3.5" />{t('wikiAuthoring.yourWork')}</div>
              <div className="flex gap-2 overflow-x-auto pb-1">
                {ownRevisions.items.map((revision) => (
                  <button key={revision.id} type="button" disabled={revision.status !== 'draft' && revision.status !== 'rejected'} onClick={() => revision.status === 'rejected' ? retryRevision.mutate(revision.id) : setAuthoringRevision(revision)} className="min-w-[210px] rounded-xl border border-white/10 bg-black/10 px-3 py-2.5 text-left transition hover:border-blue-400/30 hover:bg-white/5 disabled:cursor-default disabled:hover:border-white/10">
                    <div className="truncate text-sm font-medium text-slate-200">{revision.title}</div>
                    <div className="mt-1 flex items-center justify-between gap-2 text-xs text-slate-500"><span>v{revision.revision_number}</span><span className={revision.status === 'pending_review' ? 'text-amber-300' : revision.status === 'published' ? 'text-emerald-300' : 'text-blue-300'}>{t(`wikiAuthoring.status.${revision.status}`)}</span></div>
                    {revision.status === 'rejected' && <div className="mt-2 border-t border-white/10 pt-2 text-xs text-amber-200/80">{retryRevision.isPending && retryRevision.variables === revision.id ? t('wikiAuthoring.preparingRevision') : revision.review_note || t('wikiAuthoring.fixRevision')}</div>}
                  </button>
                ))}
              </div>
            </div>
          )}
          {reviewableRevisions && reviewableRevisions.items.length > 0 && (
            <div className="mt-4 border-t border-white/10 pt-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-cyan-300/70"><SearchCheck className="h-3.5 w-3.5" />{t('wikiPeerReview.availableTitle')}</div>
              <p className="mb-3 text-xs leading-5 text-slate-500">{t('wikiPeerReview.availableDescription')}</p>
              <div className="grid gap-2 md:grid-cols-2">
                {reviewableRevisions.items.map((revision) => (
                  <button key={revision.id} type="button" onClick={() => setReviewRevision(revision)} className="group rounded-xl border border-cyan-300/10 bg-cyan-500/[0.035] px-3 py-3 text-left transition hover:border-cyan-300/25 hover:bg-cyan-500/[0.07]">
                    <div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="truncate text-sm font-medium text-slate-200 group-hover:text-cyan-100">{revision.title}</div><div className="mt-1 line-clamp-1 text-xs text-slate-500">{revision.edit_summary || revision.summary}</div></div><SearchCheck className="h-4 w-4 shrink-0 text-cyan-300" /></div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* Search Bar */}
      <form onSubmit={handleSearch} className="mb-8 md:mb-12">
        <div className="relative max-w-2xl mx-auto">
          <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
          <input
            type="text"
            placeholder={t('wikiPage.searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-12 pr-12 py-4 bg-white/10 backdrop-blur-sm border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
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
                  className="group bg-white/10 backdrop-blur-sm border border-white/20 rounded-xl p-5 hover:bg-white/15 transition-all text-left"
                >
                  <div className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-white/[0.07] px-2.5 py-1 text-[11px] font-medium text-slate-400">
                    {article.space_key === 'guides' ? <Compass className="h-3 w-3 text-cyan-300" /> : <LibraryBig className="h-3 w-3 text-purple-300" />}
                    {article.space_key === 'guides' ? t('wikiPage.guideBadge') : t('wikiPage.knowledgeBadge')}
                  </div>
                  <h3 className="text-base font-semibold text-white mb-2 group-hover:text-blue-300 transition-colors line-clamp-2">
                    {article.title}
                  </h3>
                  <p className="text-sm text-gray-300 mb-3 line-clamp-2">{article.summary}</p>
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
            <div className="text-center py-8 bg-white/5 backdrop-blur-sm rounded-xl border border-white/10">
              <Search className="w-10 h-10 text-gray-500 mx-auto mb-3" />
              <p className="text-gray-400">{t('wikiPage.noResults')}</p>
            </div>
          )}
        </div>
      )}

      {/* Main content (hidden during search) */}
      {searchResults === null && (<>
      {guideArticles.length > 0 && (
        <section className="mb-12 overflow-hidden rounded-3xl border border-cyan-300/15 bg-gradient-to-br from-blue-500/15 via-cyan-500/[0.08] to-purple-500/10 p-5 shadow-2xl shadow-blue-950/20 md:p-7">
          <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div>
              <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-cyan-300/15 bg-cyan-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.15em] text-cyan-200"><ShieldCheck className="h-3.5 w-3.5" />{t('wikiPage.officialGuides')}</div>
              <h2 className="flex items-center gap-3 text-2xl font-bold text-white"><Compass className="h-6 w-6 text-cyan-300" />{t('wikiPage.guidesTitle')}</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">{t('wikiPage.guidesDescription')}</p>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {guideArticles.map((article, index) => (
              <button key={article.id} type="button" onClick={() => navigate(`/wiki/articles/${article.slug}`)} className="group relative overflow-hidden rounded-2xl border border-white/10 bg-[#0b1730]/70 p-5 text-left transition hover:-translate-y-0.5 hover:border-cyan-300/30 hover:bg-[#10203d]">
                <span className="absolute right-4 top-3 text-5xl font-black text-white/[0.035]">{String(index + 1).padStart(2, '0')}</span>
                <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-cyan-400 text-white shadow-lg shadow-cyan-950/30"><Compass className="h-5 w-5" /></div>
                <h3 className="relative text-base font-semibold text-white transition group-hover:text-cyan-200">{article.title}</h3>
                <p className="relative mt-2 line-clamp-3 text-sm leading-6 text-slate-400">{article.summary}</p>
                <span className="relative mt-5 inline-flex items-center gap-1 text-xs font-medium text-cyan-300">{t('wikiPage.openGuide')}<ChevronRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" /></span>
              </button>
            ))}
          </div>
        </section>
      )}

      <div className="mb-6 flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/15 text-purple-200 ring-1 ring-purple-400/20"><LibraryBig className="h-5 w-5" /></span>
        <div><h2 className="text-2xl font-bold text-white">{t('wikiPage.knowledgeTitle')}</h2><p className="mt-1 text-sm text-slate-400">{t('wikiPage.knowledgeDescription')}</p></div>
      </div>
      <div className="mb-12">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
          <BookOpen className="w-6 h-6 text-blue-400" />
          {t('wikiPage.categories')}
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {categories.map((category) => {
            const IconComponent = getIconComponent(category.icon);
            return (
              <button
                key={category.id}
                onClick={() => navigate(`/wiki/${category.slug}`)}
                className="group bg-white/10 backdrop-blur-sm border border-white/20 rounded-xl p-6 hover:bg-white/15 transition-all hover:scale-105 text-left"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-lg flex items-center justify-center">
                    <IconComponent className="w-6 h-6 text-white" />
                  </div>
                  <ChevronRight className="w-5 h-5 text-gray-400 group-hover:text-white transition-colors" />
                </div>
                <h3 className="text-lg font-semibold text-white mb-2">{category.name}</h3>
                <p className="text-sm text-gray-300 mb-3 line-clamp-2">{category.description}</p>
                <div className="text-xs text-gray-400">
                  {category.articles_count} {t('wikiPage.articles')}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Popular Articles */}
      {popularArticles.length > 0 && (
        <div className="mb-12">
          <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
            <TrendingUp className="w-6 h-6 text-yellow-400" />
            {t('wikiPage.popularArticles')}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {popularArticles.map((article) => (
              <button
                key={article.id}
                onClick={() => navigate(`/wiki/articles/${article.slug}`)}
                className="group bg-white/10 backdrop-blur-sm border border-white/20 rounded-xl p-5 hover:bg-white/15 transition-all text-left"
              >
                <h3 className="text-base font-semibold text-white mb-2 group-hover:text-blue-300 transition-colors line-clamp-2">
                  {article.title}
                </h3>
                <p className="text-sm text-gray-300 mb-3 line-clamp-2">{article.summary}</p>
                <div className="flex items-center justify-between text-xs text-gray-400">
                  <div className="flex items-center gap-1">
                    <Eye className="w-3.5 h-3.5" />
                    <span>{article.views}</span>
                  </div>
                  {article.author && (
                    <span className="text-gray-500">{article.author}</span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Recent Articles */}
      {recentArticles.length > 0 && (
        <div>
          <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
            <Clock className="w-6 h-6 text-green-400" />
            {t('wikiPage.recentArticles')}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {recentArticles.map((article) => (
              <button
                key={article.id}
                onClick={() => navigate(`/wiki/articles/${article.slug}`)}
                className="group bg-white/10 backdrop-blur-sm border border-white/20 rounded-xl p-5 hover:bg-white/15 transition-all text-left"
              >
                <h3 className="text-base font-semibold text-white mb-2 group-hover:text-blue-300 transition-colors line-clamp-2">
                  {article.title}
                </h3>
                <p className="text-sm text-gray-300 mb-3 line-clamp-2">{article.summary}</p>
                <div className="flex items-center justify-between text-xs text-gray-400">
                  <span>{new Date(article.created_at).toLocaleDateString(i18n.resolvedLanguage)}</span>
                  {article.author && (
                    <span className="text-gray-500">{article.author}</span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {categories.length === 0 && popularArticles.length === 0 && guideArticles.length === 0 && (
        <div className="text-center py-12 bg-white/5 backdrop-blur-sm rounded-2xl border border-white/10">
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


