/** Страница статьи Wiki - полный текст с Markdown */

import { useState, useEffect } from 'react';
import type { AxiosError } from 'axios';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Eye,
  Clock,
  User,
  Tag,
  Loader2,
  AlertCircle,
  ThumbsUp,
  MessageSquare,
  Check,
  FilePenLine,
  Compass,
  LibraryBig,
} from 'lucide-react';
import { wikiAPI } from '../api/client';
import type { WikiArticle, WikiFeedbackStats } from '../types/api';
import { SEOHead } from '../components/SEOHead';
import { ShareMenu } from '../components/ShareMenu';
import { WikiFeedbackModal } from '../components/WikiFeedbackModal';
import { useAuth } from '../contexts/AuthContext';
import { TableOfContents, extractHeadings } from '../components/wiki/TableOfContents';
import { MobileTocDrawer } from '../components/wiki/MobileTocDrawer';
import { WikiAuthoringModal } from '../components/wiki/WikiAuthoringModal';
import { WikiContentRenderer } from '../components/wiki/WikiContentRenderer';

export function WikiArticlePage() {
  const { t, i18n } = useTranslation();
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const [article, setArticle] = useState<WikiArticle | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);
  const [showAuthoringModal, setShowAuthoringModal] = useState(false);

  // Загружаем статью
  useEffect(() => {
    loadArticle();
  }, [slug]);

  const loadArticle = async () => {
    if (!slug) return;

    try {
      setIsLoading(true);
      setError(null);

      const articleData = await wikiAPI.getArticle(slug);
      setArticle(articleData);
    } catch (err: any) {
      console.error('Failed to load article:', err);
      if (err.response?.status === 404) {
        setError(t('wikiArticlePage.notFound'));
      } else {
        setError(t('wikiArticlePage.errorLoadFailed'));
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Загружаем статистику обратной связи
  const { data: feedbackStats } = useQuery<WikiFeedbackStats>({
    queryKey: ['wiki-feedback-stats', slug],
    queryFn: () => wikiAPI.getFeedbackStats(slug!),
    enabled: !!slug && !!article,
    staleTime: 30000, // 30 секунд
  });

  const { data: authoringCategories } = useQuery({
    queryKey: ['wiki-categories-authoring'],
    queryFn: () => wikiAPI.listCategories({ page: 1, page_size: 100 }),
    enabled: showAuthoringModal,
    staleTime: 60_000,
  });

  // Мутация для добавления "Полезно"
  const addHelpfulMutation = useMutation({
    mutationFn: () => wikiAPI.createFeedback(slug!, { feedback_type: 'helpful' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wiki-feedback-stats', slug] });
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      // Если уже отмечено как полезное - не показываем ошибку
      if (err?.response?.status !== 400) {
        console.error('Error adding helpful mark:', err);
      }
    },
  });

  // Мутация для удаления "Полезно"
  const removeHelpfulMutation = useMutation({
    mutationFn: () => wikiAPI.removeHelpfulMark(slug!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wiki-feedback-stats', slug] });
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      console.error('Error removing helpful mark:', err);
    },
  });

  const handleHelpfulClick = () => {
    if (feedbackStats?.user_marked_helpful) {
      removeHelpfulMutation.mutate();
    } else {
      addHelpfulMutation.mutate();
    }
  };

  const isHelpfulLoading = addHelpfulMutation.isPending || removeHelpfulMutation.isPending;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 text-purple-500 animate-spin" />
      </div>
    );
  }

  if (error || !article) {
    return (
      <div className="max-w-4xl mx-auto px-4 md:px-6 py-12 text-center">
        <AlertCircle className="w-16 h-16 text-red-400 mx-auto mb-4" />
        <h2 className="text-2xl font-bold text-white mb-4">{error || t('wikiArticlePage.notFound')}</h2>
        <button
          onClick={() => navigate('/wiki')}
          className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
        >
          {t('wikiArticlePage.backToWiki')}
        </button>
      </div>
    );
  }

  // JSON-LD structured data для поисковиков
  const jsonLd = article
    ? {
        '@context': 'https://schema.org',
        '@type': 'Article',
        headline: article.title,
        description: article.summary,
        image: `https://filamenthub.ru/logo.svg`,
        datePublished: article.created_at,
        dateModified: article.updated_at,
        author: {
          '@type': 'Organization',
          name: article.author || 'FilamentHub',
        },
        publisher: {
          '@type': 'Organization',
          name: 'FilamentHub',
          logo: {
            '@type': 'ImageObject',
            url: 'https://filamenthub.ru/logo.svg',
          },
        },
        mainEntityOfPage: {
          '@type': 'WebPage',
          '@id': `https://filamenthub.ru/wiki/articles/${article.slug}`,
        },
        articleSection: article.category_name || 'Wiki',
        keywords: article.tags?.join(', ') || '',
      }
    : undefined;

  return (
    <>
      {article && (
        <SEOHead
          title={article.title}
          description={article.summary}
          keywords={article.tags?.join(', ')}
          url={`/wiki/articles/${article.slug}`}
          type="article"
          author={article.author || undefined}
          publishedTime={article.created_at}
          modifiedTime={article.updated_at}
          section={article.category_name || undefined}
          tags={article.tags || undefined}
          jsonLd={jsonLd}
          allowAI={true}
        />
      )}
      {/* Main Layout: Content + Sidebar TOC */}
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-6 md:py-12">
        <div className="lg:grid lg:grid-cols-[1fr_280px] lg:gap-8">
          {/* Main Content Column */}
          <div className="max-w-4xl">
            {/* Back Button */}
            <div className="flex items-center justify-between mb-6">
              <button
                onClick={() => {
                  if (article.category_name) {
                    navigate('/wiki');
                  } else {
                    navigate('/wiki');
                  }
                }}
                className="flex items-center gap-2 text-gray-300 hover:text-white transition-colors group"
              >
                <ArrowLeft className="w-5 h-5 group-hover:-translate-x-1 transition-transform" />
                <span className="hidden sm:inline">{t('wikiArticlePage.back')}</span>
              </button>

              <div className="flex items-center gap-2">
                {user && (
                  <button type="button" onClick={() => setShowAuthoringModal(true)} className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-sm text-slate-300 transition hover:border-blue-400/30 hover:bg-blue-500/10 hover:text-white">
                    <FilePenLine className="h-4 w-4" />
                    <span className="hidden sm:inline">{t('wikiAuthoring.proposeEdit')}</span>
                  </button>
                )}
                <ShareMenu title={article.title} description={article.summary} />
              </div>
            </div>

            {/* Article Header */}
            <div className="mb-8">
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm ${article.space_key === 'guides' ? 'bg-cyan-500/15 text-cyan-200' : 'bg-purple-500/15 text-purple-200'}`}>
                  {article.space_key === 'guides' ? <Compass className="h-3.5 w-3.5" /> : <LibraryBig className="h-3.5 w-3.5" />}
                  {article.space_key === 'guides' ? t('wikiPage.guideBadge') : t('wikiPage.knowledgeBadge')}
                </span>
                {article.category_name && (
                  <span className="inline-flex items-center gap-2 px-3 py-1 bg-blue-500/20 text-blue-300 rounded-full text-sm">
                    {article.category_name}
                  </span>
                )}
                <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-400">{t(`wikiAuthoring.authorship.${article.provenance}`)}</span>
              </div>

              {/* Title */}
              <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold text-white mb-4 leading-tight">
                {article.title}
              </h1>

              {/* Meta Info and Tags */}
              <div className="flex flex-wrap items-center gap-4 text-sm text-gray-400 mb-4">
                {article.author && (
                  <div className="flex items-center gap-2">
                    <User className="w-4 h-4" />
                    <span>{article.author}</span>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4" />
                  <span>
                    {new Date(article.created_at).toLocaleDateString(i18n.resolvedLanguage, {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                    })}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Eye className="w-4 h-4" />
                  <span>{article.views} {t('wikiArticlePage.views')}</span>
                </div>
              </div>

              {/* Tags */}
              {article.tags && article.tags.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-6">
                  {article.tags.map((tag, idx) => (
                    <span
                      key={idx}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-500/20 text-blue-300 rounded-full text-xs font-semibold"
                    >
                      <Tag className="w-3 h-3" />
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Article Content (Markdown) */}
            <article className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6 md:p-8 mb-8 overflow-hidden">
              <WikiContentRenderer
                content={article.content}
                taskStorageKey={slug ? `wiki-checkboxes-${slug}` : undefined}
              />
            </article>

            {/* Article Footer - Feedback Section */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-6 bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl mb-8">
              <div className="text-gray-400 text-sm font-medium">
                {t('wikiArticlePage.wasHelpful')}
              </div>
              <div className="flex items-center gap-3">
                {/* Кнопка "Полезно" - доступна всем */}
                <button
                  onClick={handleHelpfulClick}
                  disabled={isHelpfulLoading}
                  className={`flex items-center gap-2 px-5 py-2.5 rounded-lg transition-colors border font-medium ${
                    feedbackStats?.user_marked_helpful
                      ? 'bg-green-500/30 border-green-500/50 text-green-300'
                      : 'bg-green-500/20 hover:bg-green-500/30 border-green-500/30 text-green-300'
                  } ${isHelpfulLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  {feedbackStats?.user_marked_helpful ? (
                    <Check className="w-4 h-4" />
                  ) : (
                    <ThumbsUp className="w-4 h-4" />
                  )}
                  <span>
                    {feedbackStats?.user_marked_helpful ? t('wikiArticlePage.marked') : t('wikiArticlePage.helpful')}
                    {feedbackStats && feedbackStats.helpful_count > 0 && (
                      <span className="ml-1.5 text-green-400/80">
                        ({feedbackStats.helpful_count})
                      </span>
                    )}
                  </span>
                </button>

                {/* Кнопка "Оставить отзыв" - только для авторизованных */}
                {user && (
                  <button
                    onClick={() => setShowFeedbackModal(true)}
                    className="flex items-center gap-2 px-5 py-2.5 bg-white/10 hover:bg-white/15 text-gray-300 rounded-lg transition-colors border border-white/20 font-medium"
                  >
                    <MessageSquare className="w-4 h-4" />
                    <span>{t('wikiArticlePage.leaveFeedback')}</span>
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Desktop Sidebar TOC */}
          {extractHeadings(article.content).length > 0 && (
            <aside className="hidden lg:block">
              <div className="sticky top-24">
                <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl p-4 max-h-[calc(100vh-8rem)] overflow-y-auto scrollbar-thin scrollbar-track-transparent scrollbar-thumb-white/10">
                  <TableOfContents content={article.content} />
                </div>
              </div>
            </aside>
          )}
        </div>
      </div>

      {/* Модальное окно для отзыва */}
      <WikiFeedbackModal
        isOpen={showFeedbackModal}
        onClose={() => setShowFeedbackModal(false)}
        articleSlug={article.slug}
        articleTitle={article.title}
      />
      {showAuthoringModal && authoringCategories && (
        <WikiAuthoringModal
          categories={authoringCategories.items}
          article={article}
          onClose={() => setShowAuthoringModal(false)}
          onSaved={() => {
            queryClient.invalidateQueries({ queryKey: ['wiki-own-revisions'] });
          }}
        />
      )}

      {/* Mobile TOC Drawer */}
      <MobileTocDrawer content={article.content} articleTitle={article.title} />
    </>
  );
}
