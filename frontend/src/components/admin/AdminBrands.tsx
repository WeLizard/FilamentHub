/** Компонент для управления брендами */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Building2, CheckCircle, XCircle, Shield, Search, ExternalLink } from 'lucide-react';
import { adminAPI } from '../../api/client';
import type { Brand } from '../../types/api';

type FilterType = 'all' | 'verified' | 'unverified';

export function AdminBrands() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<FilterType>('all');
  const [searchQuery, setSearchQuery] = useState('');

  // Определяем параметр verified для API
  const verifiedParam = filter === 'all' ? null : filter === 'verified' ? true : false;

  // Загрузка брендов
  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-brands', page, filter, searchQuery],
    queryFn: () => adminAPI.listBrands({
      page,
      size: 20,
      verified: verifiedParam,
      active_only: true,
      search: searchQuery || undefined,
    }),
  });

  // Верификация бренда
  const verifyMutation = useMutation({
    mutationFn: (brandId: number) => adminAPI.verifyBrand(brandId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-brands'] });
    },
  });

  // Отзыв верификации
  const unverifyMutation = useMutation({
    mutationFn: (brandId: number) => adminAPI.unverifyBrand(brandId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-brands'] });
    },
  });

  const handleFilterChange = (newFilter: FilterType) => {
    setFilter(newFilter);
    setPage(1);
  };

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    setPage(1);
  };

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">Загрузка брендов...</div>;
  }

  if (error) {
    return <div className="text-center py-12 text-red-400">Ошибка загрузки брендов</div>;
  }

  const brands = data?.items || [];
  const total = data?.total || 0;
  const pages = data?.pages || 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2">Управление брендами</h2>
          <p className="text-gray-400">Всего: {total}</p>
        </div>
      </div>

      {/* Фильтры и поиск */}
      <div className="flex flex-col sm:flex-row gap-4">
        {/* Фильтры */}
        <div className="flex gap-2">
          {(['all', 'verified', 'unverified'] as FilterType[]).map((f) => (
            <button
              key={f}
              onClick={() => handleFilterChange(f)}
              className={`
                px-4 py-2 rounded-lg transition-all text-sm
                ${filter === f
                  ? 'bg-purple-600 text-white'
                  : 'bg-white/5 text-gray-300 hover:bg-white/10'
                }
              `}
            >
              {f === 'all' ? 'Все' : f === 'verified' ? 'Верифицированные' : 'Неверифицированные'}
            </button>
          ))}
        </div>

        {/* Поиск */}
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Поиск по названию бренда..."
            className="w-full pl-10 pr-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>
      </div>

      {/* Список брендов */}
      {brands.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Building2 className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>Нет брендов для отображения</p>
        </div>
      ) : (
        <div className="space-y-4">
          {brands.map((brand) => (
            <div
              key={brand.id}
              className="bg-white/5 rounded-xl p-4 border border-white/10 hover:border-white/20 transition-all"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    <Building2 className="w-5 h-5 text-purple-400" />
                    <h3 className="text-lg font-semibold text-white">{brand.name}</h3>
                    {brand.verified ? (
                      <span className="flex items-center space-x-1 px-2 py-1 rounded bg-green-500/20 text-green-400 text-xs font-semibold">
                        <Shield className="w-3 h-3" />
                        <span>Верифицирован</span>
                      </span>
                    ) : (
                      <span className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-400 text-xs font-semibold">
                        Неверифицирован
                      </span>
                    )}
                    <button
                      onClick={() => navigate(`/brands/${brand.id}`)}
                      className="flex items-center space-x-1 px-2 py-1 rounded bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 text-xs transition-all"
                      title="Открыть страницу бренда"
                    >
                      <ExternalLink className="w-3 h-3" />
                      <span>Страница</span>
                    </button>
                  </div>
                  {brand.description && (
                    <p className="text-sm text-gray-400 mb-2">{brand.description}</p>
                  )}
                  {brand.website && (
                    <a
                      href={brand.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-purple-400 hover:text-purple-300 underline"
                    >
                      {brand.website}
                    </a>
                  )}
                  <p className="text-xs text-gray-500 mt-2">
                    Создан: {new Date(brand.created_at).toLocaleString('ru-RU')}
                  </p>
                </div>
                <div className="flex items-center space-x-2">
                  {!brand.verified ? (
                    <button
                      onClick={() => {
                        if (confirm(`Верифицировать бренд "${brand.name}"?`)) {
                          verifyMutation.mutate(brand.id);
                        }
                      }}
                      disabled={verifyMutation.isPending}
                      className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-all disabled:opacity-50"
                    >
                      <CheckCircle className="w-4 h-4" />
                      <span>Верифицировать</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        if (confirm(`Отозвать верификацию бренда "${brand.name}"?`)) {
                          unverifyMutation.mutate(brand.id);
                        }
                      }}
                      disabled={unverifyMutation.isPending}
                      className="flex items-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-all disabled:opacity-50"
                    >
                      <XCircle className="w-4 h-4" />
                      <span>Отозвать верификацию</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Пагинация */}
      {pages > 1 && (
        <div className="flex items-center justify-center space-x-2">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-4 py-2 rounded-lg bg-white/5 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-white/10"
          >
            Назад
          </button>
          <span className="text-gray-400">Страница {page} из {pages}</span>
          <button
            onClick={() => setPage(p => Math.min(pages, p + 1))}
            disabled={page === pages}
            className="px-4 py-2 rounded-lg bg-white/5 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-white/10"
          >
            Вперед
          </button>
        </div>
      )}
    </div>
  );
}


