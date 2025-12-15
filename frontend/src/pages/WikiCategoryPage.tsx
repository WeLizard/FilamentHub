/** Страница категории Wiki - список статей в категории */

import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { BookOpen, ArrowLeft, Eye, Clock, User, Loader2, AlertCircle } from 'lucide-react';
import { wikiAPI } from '../api/client';
import { SEOHead } from '../components/SEOHead';
import type { WikiCategory, WikiArticleSummary } from '../types/api';
import * as LucideIcons from 'lucide-react';

export function WikiCategoryPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const [category, setCategory] = useState<WikiCategory | null>(null);
  const [articles, setArticles] = useState<WikiArticleSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  useEffect(() => {
    loadCategoryAndArticles();
  }, [slug, currentPage]);

  const loadCategoryAndArticles = async () => {
    if (!slug) return;

    try {
      setIsLoading(true);
      setError(null);

      // Загружаем категорию
      const categoriesData = await wikiAPI.listCategories({ page: 1, page_size: 100 });
      const foundCategory = categoriesData.items.find((cat: WikiCategory) => cat.slug === slug);

      if (!foundCategory) {
        setError('Категория не найдена');
        return;
      }

      setCategory(foundCategory);

      // Загружаем статьи категории
      const articlesData = await wikiAPI.listArticles({
        category_slug: foundCategory.slug,
        published_only: true,
        page: currentPage,
        page_size: 12,
      });

      setArticles(articlesData.items);
      setTotalPages(articlesData.total_pages);
    } catch (err: any) {
      console.error('Failed to load category:', err);
      setError('Не удалось загрузить категорию');
    } finally {
      setIsLoading(false);
    }
  };

  const getIconComponent = (iconName: string | null) => {
    if (!iconName) return BookOpen;
    const IconComponent = (LucideIcons as any)[iconName];
    return IconComponent || BookOpen;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 text-purple-500 animate-spin" />
      </div>
    );
  }

  if (error || !category) {
    return (
      <div className="max-w-4xl mx-auto px-4 md:px-6 py-12 text-center">
        <AlertCircle className="w-16 h-16 text-red-400 mx-auto mb-4" />
        <h2 className="text-2xl font-bold text-white mb-4">{error || 'Категория не найдена'}</h2>
        <button
          onClick={() => navigate('/wiki')}
          className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
        >
          Вернуться к Wiki
        </button>
      </div>
    );
  }

  const IconComponent = getIconComponent(category.icon);

  return (
    <>
      {category && (
        <SEOHead
          title={`${category.name} - Wiki по 3D-печати`}
          description={category.description || `Статьи о ${category.name.toLowerCase()} в базе знаний FilamentHub`}
          url={`/wiki/${category.slug}`}
          type="website"
          allowAI={true}
        />
      )}
      <div className="max-w-6xl mx-auto px-4 md:px-6 py-6 md:py-12">
        {/* Back Button */}
      <button
        onClick={() => navigate('/wiki')}
        className="flex items-center gap-2 text-gray-300 hover:text-white mb-6 transition-colors group"
      >
        <ArrowLeft className="w-5 h-5 group-hover:-translate-x-1 transition-transform" />
        <span>Назад к Wiki</span>
      </button>

      {/* Category Header */}
      <div className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-6 md:p-8 mb-8">
        <div className="flex flex-col md:flex-row items-start md:items-center gap-4 md:gap-6">
          <div className="w-16 h-16 md:w-20 md:h-20 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-xl md:rounded-2xl flex items-center justify-center shadow-lg shadow-blue-500/25 shrink-0">
            <IconComponent className="w-8 h-8 md:w-10 md:h-10 text-white" />
          </div>
          <div className="flex-1">
            <h1 className="text-2xl md:text-4xl font-bold text-white mb-2">{category.name}</h1>
            <p className="text-base md:text-lg text-gray-300 mb-3">{category.description}</p>
            <div className="text-sm text-gray-400">
              {category.articles_count} {category.articles_count === 1 ? 'статья' : 'статей'}
            </div>
          </div>
        </div>
      </div>

      {/* Articles List */}
      {articles.length === 0 ? (
        <div className="text-center py-12 bg-white/5 backdrop-blur-sm rounded-2xl border border-white/10">
          <BookOpen className="w-16 h-16 text-gray-400 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-white mb-2">Статьи отсутствуют</h3>
          <p className="text-gray-400">В этой категории пока нет опубликованных статей</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
            {articles.map((article) => (
              <button
                key={article.id}
                onClick={() => navigate(`/wiki/articles/${article.slug}`)}
                className="group bg-white/10 backdrop-blur-sm border border-white/20 rounded-xl p-5 md:p-6 hover:bg-white/15 transition-all hover:scale-105 text-left"
              >
                {/* Article Title */}
                <h3 className="text-base md:text-lg font-semibold text-white mb-3 group-hover:text-blue-300 transition-colors line-clamp-2 min-h-[3rem]">
                  {article.title}
                </h3>

                {/* Article Summary */}
                <p className="text-sm text-gray-300 mb-4 line-clamp-3">{article.summary}</p>

                {/* Article Meta */}
                <div className="flex flex-col gap-2 text-xs text-gray-400">
                  {/* Views & Date */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1">
                      <Eye className="w-3.5 h-3.5" />
                      <span>{article.views} просмотров</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" />
                      <span>{new Date(article.created_at).toLocaleDateString('ru-RU')}</span>
                    </div>
                  </div>

                  {/* Author */}
                  {article.author && (
                    <div className="flex items-center gap-1 text-gray-500">
                      <User className="w-3.5 h-3.5" />
                      <span>{article.author}</span>
                    </div>
                  )}

                  {/* Tags */}
                  {article.tags && article.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {article.tags.slice(0, 3).map((tag, idx) => (
                        <span
                          key={idx}
                          className="px-2.5 py-1 bg-blue-500/20 text-blue-300 rounded-full text-xs font-semibold"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </button>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex justify-center items-center gap-2 mt-8">
              <button
                onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                disabled={currentPage === 1}
                className="px-4 py-2 bg-white/10 hover:bg-white/15 disabled:bg-white/5 disabled:text-gray-600 text-white rounded-lg transition-colors disabled:cursor-not-allowed"
              >
                Назад
              </button>

              <div className="flex items-center gap-2">
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  let pageNum: number;
                  if (totalPages <= 5) {
                    pageNum = i + 1;
                  } else if (currentPage <= 3) {
                    pageNum = i + 1;
                  } else if (currentPage >= totalPages - 2) {
                    pageNum = totalPages - 4 + i;
                  } else {
                    pageNum = currentPage - 2 + i;
                  }

                  return (
                    <button
                      key={pageNum}
                      onClick={() => setCurrentPage(pageNum)}
                      className={`w-10 h-10 rounded-lg transition-colors ${
                        currentPage === pageNum
                          ? 'bg-purple-600 text-white'
                          : 'bg-white/10 hover:bg-white/15 text-gray-300'
                      }`}
                    >
                      {pageNum}
                    </button>
                  );
                })}
              </div>

              <button
                onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                disabled={currentPage === totalPages}
                className="px-4 py-2 bg-white/10 hover:bg-white/15 disabled:bg-white/5 disabled:text-gray-600 text-white rounded-lg transition-colors disabled:cursor-not-allowed"
              >
                Вперёд
              </button>
            </div>
          )}
        </>
      )}
      </div>
    </>
  );
}

