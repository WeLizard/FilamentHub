/** Компонент для управления брендами */

import { useState, useEffect, useRef, FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Building2, CheckCircle, XCircle, Shield, Search, ExternalLink, Edit, X, Save, Loader2, Upload } from 'lucide-react';
import { ModalOverlay } from '../ModalOverlay';
import { adminAPI } from '../../api/client';
import { translateApiError } from '../../utils/translateApiError';
import type { Brand } from '../../types/api';
import type { AxiosError } from 'axios';

type FilterType = 'all' | 'verified' | 'unverified';

export function AdminBrands() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<FilterType>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [editingBrand, setEditingBrand] = useState<Brand | null>(null);
  const [editName, setEditName] = useState('');
  const [editSlug, setEditSlug] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editWebsite, setEditWebsite] = useState('');
  const [editLogoUrl, setEditLogoUrl] = useState('');
  const [editLogoBg, setEditLogoBg] = useState('');
  const [editError, setEditError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  // Редактирование бренда
  const updateBrandMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Parameters<typeof adminAPI.updateBrand>[1] }) => 
      adminAPI.updateBrand(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-brands'] });
      setEditingBrand(null);
      setEditError(null);
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      setEditError(translateApiError(t, error?.response?.data?.detail, t('adminBrands.updateError')));
    },
  });

  // Инициализация формы редактирования
  useEffect(() => {
    if (editingBrand) {
      setEditName(editingBrand.name || '');
      setEditSlug(editingBrand.slug || '');
      setEditDescription(editingBrand.description || '');
      setEditWebsite(editingBrand.website || '');
      setEditLogoUrl(editingBrand.logo_url || '');
      setEditLogoBg(editingBrand.logo_bg || '');
      setEditError(null);
    }
  }, [editingBrand]);

  // Обработка сохранения изменений
  const handleSaveEdit = async (e: FormEvent) => {
    e.preventDefault();
    setEditError(null);

    if (!editingBrand) return;

    if (!editName.trim()) {
      setEditError(t('adminBrands.nameRequired'));
      return;
    }

    if (!editSlug.trim()) {
      setEditError(t('adminBrands.slugRequired'));
      return;
    }

    // Валидация slug (только латиница, цифры, дефисы и подчеркивания)
    const slugRegex = /^[a-z0-9_-]+$/;
    if (!slugRegex.test(editSlug.toLowerCase())) {
      setEditError(t('adminBrands.slugInvalid'));
      return;
    }

    // Валидация URL если указан
    if (editWebsite && editWebsite.trim()) {
      try {
        new URL(editWebsite.startsWith('http') ? editWebsite : `https://${editWebsite}`);
      } catch {
        setEditError(t('adminBrands.invalidUrl'));
        return;
      }
    }

    updateBrandMutation.mutate({
      id: editingBrand.id,
      data: {
        name: editName.trim(),
        slug: editSlug.trim().toLowerCase(),
        description: editDescription.trim() || null,
        website: editWebsite.trim() || null,
        logo_url: editLogoUrl.trim() || null,
        logo_bg: editLogoBg.trim() || null,
      },
    });
  };

  const handleFilterChange = (newFilter: FilterType) => {
    setFilter(newFilter);
    setPage(1);
  };

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    setPage(1);
  };

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">{t('adminBrands.loading')}</div>;
  }

  if (error) {
    return <div className="text-center py-12 text-red-400">{t('adminBrands.loadError')}</div>;
  }

  const brands = data?.items || [];
  const total = data?.total || 0;
  const pages = data?.pages || 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2">{t('adminBrands.title')}</h2>
          <p className="text-gray-400">{t('adminBrands.total')}: {total}</p>
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
              {f === 'all' ? t('adminBrands.filterAll') : f === 'verified' ? t('adminBrands.filterVerified') : t('adminBrands.filterUnverified')}
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
            placeholder={t('adminBrands.searchPlaceholder')}
            className="w-full pl-10 pr-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>
      </div>

      {/* Список брендов */}
      {brands.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Building2 className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>{t('adminBrands.empty')}</p>
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
                        <span>{t('adminBrands.verified')}</span>
                      </span>
                    ) : (
                      <span className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-400 text-xs font-semibold">
                        {t('adminBrands.unverified')}
                      </span>
                    )}
                    <button
                      onClick={() => navigate(`/brands/${brand.id}`)}
                      className="flex items-center space-x-1 px-2 py-1 rounded bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 text-xs transition-all"
                      title={t('adminBrands.openPageTitle')}
                    >
                      <ExternalLink className="w-3 h-3" />
                      <span>{t('adminBrands.page')}</span>
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
                    {t('adminBrands.created')}: {new Date(brand.created_at).toLocaleString('ru-RU')}
                  </p>
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setEditingBrand(brand)}
                    className="flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-all"
                    title={t('adminBrands.editTitle')}
                  >
                    <Edit className="w-4 h-4" />
                    <span>{t('adminBrands.edit')}</span>
                  </button>
                  {!brand.verified ? (
                    <button
                      onClick={() => {
                        if (confirm(t('adminBrands.confirmVerify', { name: brand.name }))) {
                          verifyMutation.mutate(brand.id);
                        }
                      }}
                      disabled={verifyMutation.isPending}
                      className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-all disabled:opacity-50"
                    >
                      <CheckCircle className="w-4 h-4" />
                      <span>{t('adminBrands.verify')}</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        if (confirm(t('adminBrands.confirmUnverify', { name: brand.name }))) {
                          unverifyMutation.mutate(brand.id);
                        }
                      }}
                      disabled={unverifyMutation.isPending}
                      className="flex items-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-all disabled:opacity-50"
                    >
                      <XCircle className="w-4 h-4" />
                      <span>{t('adminBrands.unverify')}</span>
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
            {t('adminBrands.prev')}
          </button>
          <span className="text-gray-400">{t('adminBrands.pageOf', { page, pages })}</span>
          <button
            onClick={() => setPage(p => Math.min(pages, p + 1))}
            disabled={page === pages}
            className="px-4 py-2 rounded-lg bg-white/5 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-white/10"
          >
            {t('adminBrands.next')}
          </button>
        </div>
      )}

      {/* Модальное окно редактирования бренда */}
      {editingBrand && (
        <ModalOverlay onClose={() => { setEditingBrand(null); setEditError(null); }}>
          <div className="bg-gray-900 rounded-xl border border-white/20 p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-2xl font-bold text-white">{t('adminBrands.editTitle')}</h3>
              <button
                onClick={() => {
                  setEditingBrand(null);
                  setEditError(null);
                }}
                className="text-gray-400 hover:text-white transition-colors"
                aria-label={t('adminBrands.close')}
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            <form onSubmit={handleSaveEdit} className="space-y-4">
              {editError && (
                <div className="bg-red-500/20 border border-red-500/50 rounded-lg p-3 text-red-400 text-sm">
                  {editError}
                </div>
              )}

              <div>
                <label htmlFor="edit-name" className="block text-sm font-medium text-gray-300 mb-2">
                  {t('adminBrands.brandName')} <span className="text-red-400">*</span>
                </label>
                <input
                  id="edit-name"
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  required
                  className="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder={t('adminBrands.brandNamePlaceholder')}
                />
              </div>

              <div>
                <label htmlFor="edit-slug" className="block text-sm font-medium text-gray-300 mb-2">
                  Slug (URL) <span className="text-red-400">*</span>
                </label>
                <input
                  id="edit-slug"
                  type="text"
                  value={editSlug}
                  onChange={(e) => setEditSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))}
                  required
                  className="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="brand-slug"
                />
                <p className="text-xs text-gray-500 mt-1">{t('adminBrands.slugHint')}</p>
              </div>

              <div>
                <label htmlFor="edit-description" className="block text-sm font-medium text-gray-300 mb-2">
                  {t('adminBrands.description')}
                </label>
                <textarea
                  id="edit-description"
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  rows={3}
                  className="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                  placeholder={t('adminBrands.descriptionPlaceholder')}
                />
              </div>

              <div>
                <label htmlFor="edit-website" className="block text-sm font-medium text-gray-300 mb-2">
                  {t('adminBrands.website')}
                </label>
                <input
                  id="edit-website"
                  type="url"
                  value={editWebsite}
                  onChange={(e) => setEditWebsite(e.target.value)}
                  className="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="https://example.com"
                />
              </div>

              <div>
                <label htmlFor="edit-logo-url" className="block text-sm font-medium text-gray-300 mb-2">
                  {t('adminBrands.logoUrl')}
                </label>
                <div className="flex gap-2">
                  <input
                    id="edit-logo-url"
                    type="text"
                    value={editLogoUrl}
                    onChange={(e) => setEditLogoUrl(e.target.value)}
                    className="flex-1 px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder={t('adminBrands.logoUrlPlaceholder')}
                  />
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".png,.jpg,.jpeg,.webp,.svg"
                    className="hidden"
                    onChange={async (e) => {
                      const file = e.target.files?.[0];
                      if (!file || !editingBrand) return;
                      setIsUploading(true);
                      setEditError(null);
                      try {
                        const updated = await adminAPI.uploadBrandLogo(editingBrand.id, file);
                        setEditLogoUrl(updated.logo_url || '');
                        queryClient.invalidateQueries({ queryKey: ['admin-brands'] });
                      } catch (err: any) {
                        setEditError(translateApiError(t, err?.response?.data?.detail, t('adminBrands.uploadError')));
                      } finally {
                        setIsUploading(false);
                        if (fileInputRef.current) fileInputRef.current.value = '';
                      }
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isUploading}
                    className="flex items-center space-x-1 px-3 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-all disabled:opacity-50 whitespace-nowrap"
                  >
                    {isUploading ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Upload className="w-4 h-4" />
                    )}
                    <span>{t('adminBrands.uploadLogo')}</span>
                  </button>
                </div>
                {editLogoUrl && (
                  <div className="mt-2 flex items-center space-x-3">
                    <img
                      src={editLogoUrl}
                      alt="Logo preview"
                      className="h-10 w-10 object-contain rounded bg-white/10 p-1"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                    <span className="text-xs text-gray-400 truncate">{editLogoUrl}</span>
                  </div>
                )}
                <div className="mt-3">
                  <label className="block text-sm text-gray-300 mb-1">{t('brandProfile.logoBgLabel')}</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={editLogoBg || '#ffffff'}
                      onChange={(e) => setEditLogoBg(e.target.value)}
                      className="h-9 w-10 shrink-0 rounded border border-white/20 bg-white/10 cursor-pointer"
                    />
                    <input
                      type="text"
                      value={editLogoBg}
                      onChange={(e) => setEditLogoBg(e.target.value)}
                      placeholder="#FFFFFF"
                      className="flex-1 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                    {editLogoBg && (
                      <button
                        type="button"
                        onClick={() => setEditLogoBg('')}
                        className="px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-gray-300 hover:text-white hover:bg-white/20 text-sm whitespace-nowrap"
                      >
                        {t('brandProfile.logoBgReset')}
                      </button>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-end space-x-3 pt-4">
                <button
                  type="button"
                  onClick={() => {
                    setEditingBrand(null);
                    setEditError(null);
                  }}
                  className="px-4 py-2 bg-white/5 hover:bg-white/10 text-gray-300 rounded-lg transition-all"
                >
                  {t('adminBrands.cancel')}
                </button>
                <button
                  type="submit"
                  disabled={updateBrandMutation.isPending}
                  className="flex items-center space-x-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-all disabled:opacity-50"
                >
                  {updateBrandMutation.isPending ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>{t('adminBrands.saving')}</span>
                    </>
                  ) : (
                    <>
                      <Save className="w-4 h-4" />
                      <span>{t('adminBrands.save')}</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}


