/** Страница статьи Wiki - полный текст с Markdown */

import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Eye,
  Clock,
  User,
  Tag,
  Loader2,
  AlertCircle,
  Share2,
  ThumbsUp,
  MessageSquare,
} from 'lucide-react';
import { wikiAPI } from '../api/client';
import type { WikiArticle } from '../types/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useEffect, useRef } from 'react';
import mermaid from 'mermaid';

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
        }
      });
      mermaid.run({ nodes: [ref.current] });
    }
  }, [chart]);

  return <div ref={ref} className="mermaid my-6">{chart}</div>;
}

export function WikiArticlePage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const [article, setArticle] = useState<WikiArticle | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

      // Увеличиваем счётчик просмотров (TODO: реализовать на бэке)
      // await wikiAPI.incrementViews(slug);
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

  const handleShare = () => {
    if (navigator.share && article) {
      navigator
        .share({
          title: article.title,
          text: article.summary,
          url: window.location.href,
        })
        .catch((err) => console.log('Share failed:', err));
    } else {
      // Fallback: копируем ссылку в буфер обмена
      navigator.clipboard.writeText(window.location.href);
      alert('Ссылка скопирована в буфер обмена!');
    }
  };

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

  return (
    <div className="max-w-4xl mx-auto px-4 md:px-6 py-6 md:py-12">
      {/* Back Button */}
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={() => {
            if (article.category_name) {
              // TODO: нужно получить slug категории
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

        <button
          onClick={handleShare}
          className="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/15 text-white rounded-lg transition-colors"
        >
          <Share2 className="w-4 h-4" />
          <span className="hidden sm:inline">Поделиться</span>
        </button>
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
            <span>{new Date(article.created_at).toLocaleDateString('ru-RU', { 
              year: 'numeric', 
              month: 'long', 
              day: 'numeric' 
            })}</span>
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
      <article className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6 md:p-8 mb-8">
        <div className="prose prose-invert prose-lg max-w-none
          prose-headings:text-white prose-headings:font-bold prose-headings:mt-8 prose-headings:mb-4
          prose-h1:text-3xl prose-h1:border-b prose-h1:border-white/20 prose-h1:pb-3
          prose-h2:text-2xl prose-h2:mt-8 prose-h2:mb-4
          prose-h3:text-xl prose-h3:mt-6 prose-h3:mb-3
          prose-p:text-gray-300 prose-p:leading-7 prose-p:my-4
          prose-a:text-blue-400 prose-a:no-underline hover:prose-a:text-blue-300 hover:prose-a:underline
          prose-strong:text-white prose-strong:font-semibold
          prose-code:text-cyan-300 prose-code:bg-black/40 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm
          prose-pre:bg-black/60 prose-pre:border prose-pre:border-white/20 prose-pre:rounded-lg prose-pre:p-4 prose-pre:overflow-x-auto
          prose-blockquote:border-l-4 prose-blockquote:border-blue-500 prose-blockquote:pl-6 prose-blockquote:pr-4 prose-blockquote:py-2 prose-blockquote:bg-blue-500/10 prose-blockquote:text-gray-300 prose-blockquote:my-6 prose-blockquote:rounded-r-lg
          prose-ul:text-gray-300 prose-ul:my-4 prose-ul:space-y-2
          prose-ol:text-gray-300 prose-ol:my-4 prose-ol:space-y-2
          prose-li:text-gray-300 prose-li:marker:text-blue-400 prose-li:pl-2
          prose-table:w-full prose-table:my-6 prose-table:border-collapse
          prose-thead:bg-white/10
          prose-th:border prose-th:border-white/30 prose-th:px-4 prose-th:py-3 prose-th:text-left prose-th:text-white prose-th:font-semibold
          prose-tbody:bg-white/5
          prose-td:border prose-td:border-white/20 prose-td:px-4 prose-td:py-3 prose-td:text-gray-300
          prose-tr:hover:bg-white/10
          prose-img:rounded-xl prose-img:shadow-xl prose-img:my-6
          prose-hr:border-white/20 prose-hr:my-8
        ">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code(props: any) {
                const {node, inline, className, children, ...rest} = props;
                const match = /language-(\w+)/.exec(className || '');
                
                // Mermaid диаграммы
                if (!inline && match && match[1] === 'mermaid') {
                  const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
                  return <MermaidDiagram chart={String(children).replace(/\n$/, '')} id={id} />;
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
              img(props: any) {
                const {src, alt, ...rest} = props;
                // Если путь относительный, добавляем базовый URL для изображений
                let imageSrc = src;
                if (src && !src.startsWith('http') && !src.startsWith('/')) {
                  // Относительный путь - ищем в uploads или используем абсолютный
                  imageSrc = src.startsWith('uploads/') ? `/api/v1/${src}` : src;
                }
                return (
                  <img 
                    src={imageSrc} 
                    alt={alt || ''} 
                    className="max-w-full h-auto rounded-xl shadow-xl my-6"
                    {...rest}
                  />
                );
              },
            }}
          >
            {article.content}
          </ReactMarkdown>
        </div>
      </article>

      {/* Article Footer */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-6 bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl mb-8">
        <div className="text-gray-400 text-sm font-medium">
          Была ли эта статья полезна?
        </div>
        <div className="flex items-center gap-3">
          <button className="flex items-center gap-2 px-5 py-2.5 bg-green-500/20 hover:bg-green-500/30 text-green-300 rounded-lg transition-colors border border-green-500/30 font-medium">
            <ThumbsUp className="w-4 h-4" />
            <span>Полезно</span>
          </button>
          <button className="flex items-center gap-2 px-5 py-2.5 bg-white/10 hover:bg-white/15 text-gray-300 rounded-lg transition-colors border border-white/20 font-medium">
            <MessageSquare className="w-4 h-4" />
            <span>Оставить отзыв</span>
          </button>
        </div>
      </div>
    </div>
  );
}

