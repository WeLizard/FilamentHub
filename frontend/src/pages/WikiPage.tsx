/** Главная страница Wiki - каталог знаний о 3D печати */

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, Search, TrendingUp, Clock, Eye, ChevronRight, Loader2 } from 'lucide-react';
import { wikiAPI } from '../api/client';
import { SEOHead } from '../components/SEOHead';
import type { WikiCategory, WikiArticleSummary } from '../types/api';

// Маппинг названий иконок Lucide на компоненты
import * as LucideIcons from 'lucide-react';

export function WikiPage() {
  const navigate = useNavigate();
  const [categories, setCategories] = useState<WikiCategory[]>([]);
  const [popularArticles, setPopularArticles] = useState<WikiArticleSummary[]>([]);
  const [recentArticles, setRecentArticles] = useState<WikiArticleSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Загружаем категории
      const categoriesData = await wikiAPI.listCategories({ page: 1, page_size: 50 });
      setCategories(categoriesData.items);

      // Загружаем популярные статьи (TODO: сортировка по views на бэке)
      const articlesData = await wikiAPI.listArticles({ page: 1, page_size: 6, published_only: true });
      
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
      setError('Не удалось загрузить данные Wiki');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim().length < 2) return;
    
    try {
      const results = await wikiAPI.searchArticles(searchQuery);
      // TODO: показать результаты поиска в модалке или на отдельной странице
      console.log('Search results:', results);
    } catch (err) {
      console.error('Search failed:', err);
    }
  };

  const getIconComponent = (iconName: string | null) => {
    if (!iconName) return BookOpen;
    
    // Преобразуем имя иконки в PascalCase если нужно
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

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-400">{error}</p>
        <button
          onClick={loadData}
          className="mt-4 px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
        >
          Повторить попытку
        </button>
      </div>
    );
  }

  return (
    <>
      <SEOHead
        title="Wiki по 3D-печати"
        description="База знаний о 3D-печати: материалы, настройки, решение проблем. Гайды для новичков и профессионалов."
        keywords="3D печать, Wiki, гайды, материалы, настройки печати, решение проблем, PLA, PETG, ABS"
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
          <h1 className="text-3xl md:text-4xl font-bold text-white">3D Print Wiki</h1>
        </div>
        <p className="text-base md:text-xl text-gray-300 max-w-2xl mx-auto">
          База знаний о материалах, технологиях и решении проблем 3D печати
        </p>
      </div>

      {/* Search Bar */}
      <form onSubmit={handleSearch} className="mb-8 md:mb-12">
        <div className="relative max-w-2xl mx-auto">
          <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
          <input
            type="text"
            placeholder="Поиск по материалам, проблемам, технологиям..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-12 pr-4 py-4 bg-white/10 backdrop-blur-sm border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
          />
        </div>
      </form>

      {/* Categories Grid */}
      <div className="mb-12">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
          <BookOpen className="w-6 h-6 text-blue-400" />
          Категории
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
                  {category.articles_count} {category.articles_count === 1 ? 'статья' : 'статей'}
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
            Популярные статьи
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
                    <span className="text-gray-500">by {article.author}</span>
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
            Недавние статьи
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
                  <span>{new Date(article.created_at).toLocaleDateString('ru-RU')}</span>
                  {article.author && (
                    <span className="text-gray-500">by {article.author}</span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {categories.length === 0 && popularArticles.length === 0 && (
        <div className="text-center py-12 bg-white/5 backdrop-blur-sm rounded-2xl border border-white/10">
          <BookOpen className="w-16 h-16 text-gray-400 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-white mb-2">Wiki в разработке</h3>
          <p className="text-gray-400">
            Скоро здесь появятся статьи о материалах и технологиях 3D печати
          </p>
        </div>
      )}
      </div>
    </>
  );
}


