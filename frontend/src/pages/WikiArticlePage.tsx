/** Страница статьи Wiki - полный текст с Markdown */

import { useState, useEffect, useRef } from 'react';
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
} from 'lucide-react';
import { wikiAPI } from '../api/client';
import type { WikiArticle, WikiFeedbackStats } from '../types/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import mermaid from 'mermaid';
import { SEOHead } from '../components/SEOHead';
import { ShareMenu } from '../components/ShareMenu';
import { WikiFeedbackModal } from '../components/WikiFeedbackModal';
import { useAuth } from '../contexts/AuthContext';
import { TableOfContents, generateHeadingId, extractHeadings } from '../components/wiki/TableOfContents';
import { MobileTocDrawer } from '../components/wiki/MobileTocDrawer';

// Mermaid диаграмма компонент
function MermaidDiagram({ chart, id }: { chart: string; id: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current && chart) {
      mermaid.initialize({
        startOnLoad: false,
        theme: 'dark',
        themeVariables: {
          background: '#1a1a1a',
          primaryColor: '#6366f1',
          primaryTextColor: '#fff',
          primaryBorderColor: '#818cf8',
          lineColor: '#9ca3af',
          secondaryColor: '#374151',
          tertiaryColor: '#111827',
        },
      });
      mermaid.run({ nodes: [ref.current] });
    }
  }, [chart]);

  return (
    <div ref={ref} className="mermaid my-6">
      {chart}
    </div>
  );
}

export function WikiArticlePage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const [article, setArticle] = useState<WikiArticle | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);

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
        setError('Статья не найдена');
      } else {
        setError('Не удалось загрузить статью');
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Загружаем статистику обратной связи
  const { data: feedbackStats, refetch: refetchStats } = useQuery<WikiFeedbackStats>({
    queryKey: ['wiki-feedback-stats', slug],
    queryFn: () => wikiAPI.getFeedbackStats(slug!),
    enabled: !!slug && !!article,
    staleTime: 30000, // 30 секунд
  });

  // Мутация для добавления "Полезно"
  const addHelpfulMutation = useMutation({
    mutationFn: () => wikiAPI.createFeedback(slug!, { feedback_type: 'helpful' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wiki-feedback-stats', slug] });
    },
    onError: (err: any) => {
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
    onError: (err: any) => {
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
        <h2 className="text-2xl font-bold text-white mb-4">{error || 'Статья не найдена'}</h2>
        <button
          onClick={() => navigate('/wiki')}
          className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
        >
          Вернуться к Wiki
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
        <div className="lg:grid lg:grid-cols-[1fr,280px] lg:gap-8">
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
                <span className="hidden sm:inline">Назад</span>
              </button>

              <ShareMenu title={article.title} description={article.summary} />
            </div>

            {/* Article Header */}
            <div className="mb-8">
              {/* Category Badge */}
              {article.category_name && (
                <div className="mb-4">
                  <span className="inline-flex items-center gap-2 px-3 py-1 bg-blue-500/20 text-blue-300 rounded-full text-sm">
                    {article.category_name}
                  </span>
                </div>
              )}

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
                    {new Date(article.created_at).toLocaleDateString('ru-RU', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                    })}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Eye className="w-4 h-4" />
                  <span>{article.views} просмотров</span>
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
              <div
                className="prose prose-lg max-w-none break-words text-gray-200
                  [&>*]:text-gray-200
                  [&_h1]:text-white [&_h1]:font-bold [&_h1]:text-3xl [&_h1]:mt-8 [&_h1]:mb-4 [&_h1]:border-b [&_h1]:border-white/20 [&_h1]:pb-3
                  [&_h2]:text-white [&_h2]:font-bold [&_h2]:text-2xl [&_h2]:mt-8 [&_h2]:mb-4
                  [&_h3]:text-white [&_h3]:font-bold [&_h3]:text-xl [&_h3]:mt-6 [&_h3]:mb-3
                  [&_h4]:text-white [&_h4]:font-semibold [&_h4]:text-lg [&_h4]:mt-4 [&_h4]:mb-2
                  [&_p]:text-gray-200 [&_p]:leading-7 [&_p]:my-4 [&_p]:break-words
                  [&_a]:text-blue-400 [&_a]:no-underline hover:[&_a]:text-blue-300 hover:[&_a]:underline
                  [&_strong]:text-white [&_strong]:font-semibold
                  [&_em]:text-gray-200
                  [&_code]:text-cyan-300 [&_code]:bg-black/40 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-sm
                  [&_pre]:bg-black/60 [&_pre]:border [&_pre]:border-white/20 [&_pre]:rounded-lg [&_pre]:p-4 [&_pre]:overflow-x-auto
                  [&_blockquote]:border-l-4 [&_blockquote]:border-blue-500 [&_blockquote]:pl-6 [&_blockquote]:pr-4 [&_blockquote]:py-2 [&_blockquote]:bg-blue-500/10 [&_blockquote]:text-gray-200 [&_blockquote]:my-6 [&_blockquote]:rounded-r-lg
                  [&_ul]:text-gray-200 [&_ul]:my-4 [&_ul]:space-y-2 [&_ul]:list-disc [&_ul]:pl-6
                  [&_ol]:text-gray-200 [&_ol]:my-4 [&_ol]:space-y-2 [&_ol]:list-decimal [&_ol]:pl-6
                  [&_li]:text-gray-200 [&_li]:marker:text-blue-400 [&_li]:pl-2
                  [&_img]:rounded-xl [&_img]:shadow-xl [&_img]:my-6 [&_img]:max-w-full [&_img]:h-auto
                  [&_hr]:border-white/20 [&_hr]:my-8
                >
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                code(props: any) {
                  const { node, inline, className, children, ...rest } = props;
                  const match = /language-(\w+)/.exec(className || '');

                  // Mermaid диаграммы
                  if (!inline && match && match[1] === 'mermaid') {
                    const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
                    return (
                      <MermaidDiagram chart={String(children).replace(/\n$/, '')} id={id} />
                    );
                  }

                  // Обычный code блок
                  if (!inline && match) {
                    return (
                      <SyntaxHighlighter
                        style={vscDarkPlus as any}
                        language={match[1]}
                        PreTag="div"
                      >
                        {String(children).replace(/\n$/, '')}
                      </SyntaxHighlighter>
                    );
                  }

                  // Inline code
                  return (
                    <code className={className} {...rest}>
                      {children}
                    </code>
                  );
                },
                table(props: any) {
                  const { children, ...rest } = props;
                  return (
                    <div className="overflow-x-auto my-6 -mx-2 px-2">
                      <table
                        className="w-full border-collapse rounded-lg overflow-hidden text-sm
                        [&_thead]:bg-white/10
                        [&_th]:px-3 [&_th]:py-2.5 [&_th]:text-left [&_th]:text-white [&_th]:font-semibold [&_th]:border-b [&_th]:border-white/20
                        [&_tbody]:bg-white/5
                        [&_td]:px-3 [&_td]:py-2.5 [&_td]:text-gray-200 [&_td]:border-b [&_td]:border-white/10
                        [&_tr:hover]:bg-white/10
                        [&_tr:last-child_td]:border-b-0"
                        {...rest}
                      >
                        {children}
                      </table>
                    </div>
                  );
                },
                img(props: any) {
                  const { src, alt, ...rest } = props;
                  // Картинки: используй /wiki-images/filename.webp в markdown
                  return (
                    <img
                      src={src}
                      alt={alt || ''}
                      className="max-w-full h-auto rounded-xl shadow-xl my-6"
                      loading="lazy"
                      {...rest}
                    />
                  );
                },
                // Добавляем ID к заголовкам для навигации TOC
                h1(props: any) {
                  const { children, ...rest } = props;
                  const text = String(children);
                  const id = generateHeadingId(text);
                  return (
                    <h1 id={id} className="scroll-mt-24" {...rest}>
                      {children}
                    </h1>
                  );
                },
                h2(props: any) {
                  const { children, ...rest } = props;
                  const text = String(children);
                  const id = generateHeadingId(text);
                  return (
                    <h2 id={id} className="scroll-mt-24" {...rest}>
                      {children}
                    </h2>
                  );
                },
                h3(props: any) {
                  const { children, ...rest } = props;
                  const text = String(children);
                  const id = generateHeadingId(text);
                  return (
                    <h3 id={id} className="scroll-mt-24" {...rest}>
                      {children}
                    </h3>
                  );
                },
                  }}
                >
                  {article.content}
                </ReactMarkdown>
              </div>
            </article>

            {/* Article Footer - Feedback Section */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-6 bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl mb-8">
              <div className="text-gray-400 text-sm font-medium">
                Была ли эта статья полезна?
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
                    {feedbackStats?.user_marked_helpful ? 'Отмечено' : 'Полезно'}
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
                    <span>Оставить отзыв</span>
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

      {/* Mobile TOC Drawer */}
      <MobileTocDrawer content={article.content} articleTitle={article.title} />
    </>
  );
}
