/** Компонент для управления брендами */

import { useDeferredValue, useState, useEffect, useRef, FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Building2, CheckCircle, XCircle, Shield, Search, ExternalLink, Edit, X, Save, Loader2, Upload, Send, Copy, Plus } from 'lucide-react';
import { ModalOverlay } from '../ModalOverlay';
import { BrandLogoFrame } from '../BrandLogoFrame';
import { adminAPI, brandInvitesAPI } from '../../api/client';
import { translateApiError } from '../../utils/translateApiError';
import type { Brand, BrandInviteBatchPreview, BrandInviteBatchSendResult } from '../../types/api';
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
  const [showSlugRename, setShowSlugRename] = useState(false);
  const [editDescription, setEditDescription] = useState('');
  const [editWebsite, setEditWebsite] = useState('');
  const [editLogoUrl, setEditLogoUrl] = useState('');
  const [editLogoBg, setEditLogoBg] = useState('');
  const [editError, setEditError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Приглашение бренда
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteRecipients, setInviteRecipients] = useState('');
  const [inviteBrandName, setInviteBrandName] = useState('');
  const [inviteBrandId, setInviteBrandId] = useState<number | null>(null);
  const [inviteBrandFocused, setInviteBrandFocused] = useState(false);
  const [inviteSenderProfile, setInviteSenderProfile] = useState<'partnerships' | 'pr' | 'transactional'>('partnerships');
  const [invitePreview, setInvitePreview] = useState<BrandInviteBatchPreview | null>(null);
  const [inviteResult, setInviteResult] = useState<BrandInviteBatchSendResult | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteSubmitting, setInviteSubmitting] = useState(false);
  const deferredInviteBrandSearch = useDeferredValue(inviteBrandName.trim());

  const { data: inviteBrandsData, isFetching: inviteBrandsLoading } = useQuery({
    queryKey: ['admin-brand-invite-search', deferredInviteBrandSearch],
    queryFn: () => adminAPI.listBrands({
      page: 1,
      size: 8,
      active_only: true,
      search: deferredInviteBrandSearch || undefined,
    }),
    enabled: showInviteModal,
    staleTime: 30_000,
  });

  const inviteBrandMatches = inviteBrandsData?.items ?? [];
  const exactInviteBrand = inviteBrandMatches.find(
    (brand) => brand.name.localeCompare(inviteBrandName.trim(), undefined, { sensitivity: 'accent' }) === 0,
  );
  const selectedInviteBrand = inviteBrandMatches.find((brand) => brand.id === inviteBrandId) ?? null;

  const submitInvitePreview = async (e: FormEvent) => {
    e.preventDefault();
    setInviteError(null);
    setInviteSubmitting(true);
    try {
      const existingBrand = selectedInviteBrand ?? exactInviteBrand ?? null;
      const preview = await brandInvitesAPI.adminPreviewBatch({
        recipients: inviteRecipients,
        target_type: existingBrand ? 'existing' : 'new',
        brand_id: existingBrand?.id ?? null,
        brand_name: existingBrand ? null : inviteBrandName.trim(),
        member_role: 'owner',
        sender_profile: inviteSenderProfile,
      });
      setInvitePreview(preview);
    } catch (err) {
      const detail = (err as AxiosError<{ detail?: unknown }>)?.response?.data?.detail;
      setInviteError(translateApiError(t, detail, t('adminBrands.inviteError')));
    } finally {
      setInviteSubmitting(false);
    }
  };

  const confirmInviteBatch = async () => {
    if (!invitePreview?.confirmation_token || invitePreview.send_emails.length === 0) return;
    setInviteError(null);
    setInviteSubmitting(true);
    try {
      const existingBrand = selectedInviteBrand ?? exactInviteBrand ?? null;
      const result = await brandInvitesAPI.adminCreateBatch({
        emails: invitePreview.send_emails,
        confirmation_token: invitePreview.confirmation_token,
        target_type: existingBrand ? 'existing' : 'new',
        brand_id: existingBrand?.id ?? null,
        brand_name: existingBrand ? null : inviteBrandName.trim(),
        member_role: 'owner',
        sender_profile: inviteSenderProfile,
      });
      setInviteResult(result);
      setInvitePreview(null);
    } catch (err) {
      const detail = (err as AxiosError<{ detail?: unknown }>)?.response?.data?.detail;
      setInviteError(translateApiError(t, detail, t('adminBrands.inviteError')));
    } finally {
      setInviteSubmitting(false);
    }
  };

  const closeInvite = () => {
    setShowInviteModal(false);
    setInviteRecipients('');
    setInviteBrandName('');
    setInviteBrandId(null);
    setInviteBrandFocused(false);
    setInviteSenderProfile('partnerships');
    setInvitePreview(null);
    setInviteResult(null);
    setInviteError(null);
  };

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

  const renameSlugMutation = useMutation({
    mutationFn: ({ id, slug, expectedCurrentSlug }: { id: number; slug: string; expectedCurrentSlug: string }) =>
      adminAPI.renameBrandSlug(id, {
        slug,
        expected_current_slug: expectedCurrentSlug,
      }),
    onSuccess: (updatedBrand) => {
      queryClient.invalidateQueries({ queryKey: ['admin-brands'] });
      queryClient.invalidateQueries({ queryKey: ['brand'] });
      setEditingBrand(updatedBrand);
      setEditSlug(updatedBrand.slug);
      setShowSlugRename(false);
      setEditError(null);
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      setEditError(translateApiError(t, error?.response?.data?.detail, t('adminBrands.slugRenameError')));
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
      setShowSlugRename(false);
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
        description: editDescription.trim() || null,
        website: editWebsite.trim() || null,
        logo_url: editLogoUrl.trim() || null,
        logo_bg: editLogoBg.trim() || null,
      },
    });
  };

  const handleRenameSlug = () => {
    if (!editingBrand) return;
    const nextSlug = editSlug.trim().toLowerCase();
    if (!nextSlug) {
      setEditError(t('adminBrands.slugRequired'));
      return;
    }
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(nextSlug) || /^\d+$/.test(nextSlug)) {
      setEditError(t('adminBrands.slugInvalid'));
      return;
    }
    renameSlugMutation.mutate({
      id: editingBrand.id,
      slug: nextSlug,
      expectedCurrentSlug: editingBrand.slug,
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
        <button
          type="button"
          onClick={() => { setShowInviteModal(true); setInviteResult(null); setInviteError(null); }}
          className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all text-sm whitespace-nowrap"
        >
          <Send className="w-4 h-4" /> {t('adminBrands.inviteButton')}
        </button>
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
                      onClick={() => navigate(`/brands/${brand.slug}`)}
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
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <span className="block text-sm font-medium text-gray-300">{t('adminBrands.publicUrl')}</span>
                    <span className="text-sm font-mono text-cyan-300">/brands/{editingBrand.slug}</span>
                  </div>
                  {!showSlugRename && (
                    <button
                      type="button"
                      onClick={() => {
                        setEditSlug(editingBrand.slug);
                        setShowSlugRename(true);
                        setEditError(null);
                      }}
                      className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-gray-200 transition hover:bg-white/10"
                    >
                      {t('adminBrands.changePublicUrl')}
                    </button>
                  )}
                </div>
                {showSlugRename && (
                  <div className="mt-3 rounded-xl border border-amber-400/30 bg-amber-500/10 p-3">
                    <p className="mb-3 text-xs text-amber-100">{t('adminBrands.slugRenameWarning')}</p>
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <input
                        id="edit-slug"
                        type="text"
                        value={editSlug}
                        onChange={(e) => setEditSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                        className="min-w-0 flex-1 rounded-lg border border-white/20 bg-black/20 px-4 py-2 font-mono text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-400"
                        placeholder="brand-slug"
                      />
                      <button
                        type="button"
                        onClick={handleRenameSlug}
                        disabled={renameSlugMutation.isPending || editSlug === editingBrand.slug}
                        className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-gray-950 transition hover:bg-amber-400 disabled:opacity-50"
                      >
                        {renameSlugMutation.isPending ? t('adminBrands.saving') : t('adminBrands.confirmSlugRename')}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setEditSlug(editingBrand.slug);
                          setShowSlugRename(false);
                          setEditError(null);
                        }}
                        className="rounded-lg border border-white/15 px-3 py-2 text-sm text-gray-300 transition hover:bg-white/10"
                      >
                        {t('adminBrands.cancel')}
                      </button>
                    </div>
                  </div>
                )}
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
                    accept=".png,.jpg,.jpeg,.bmp,.webp"
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
                    <BrandLogoFrame
                      src={editLogoUrl}
                      alt={editName || editingBrand.name}
                      backgroundColor={editLogoBg}
                      size="thumbnail"
                      onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
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

      {showInviteModal && (
        <ModalOverlay onClose={closeInvite}>
          <div className="flex max-h-[calc(100vh-2rem)] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-white/20 bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 shadow-2xl">
            <div className="flex items-center justify-between p-6 border-b border-white/10">
              <div className="flex items-center gap-2">
                <Send className="w-5 h-5 text-purple-400" />
                <h3 className="text-xl font-bold text-white">{t('adminBrands.inviteTitle')}</h3>
              </div>
              <button onClick={closeInvite} className="text-gray-400 hover:text-white transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            {inviteResult ? (
              <div className="space-y-4 overflow-y-auto p-6">
                <div className="flex items-start gap-3 rounded-xl border border-green-400/20 bg-green-400/10 p-4">
                  <CheckCircle className="mt-0.5 h-5 w-5 shrink-0 text-green-300" />
                  <div>
                    <p className="font-medium text-green-200">
                      {t('adminBrands.inviteBatchSent', { count: inviteResult.invites.length })}
                    </p>
                    {inviteResult.skipped_existing.length > 0 && (
                      <p className="mt-1 text-xs text-green-200/70">
                        {t('adminBrands.inviteBatchSkippedExisting', { count: inviteResult.skipped_existing.length })}
                      </p>
                    )}
                  </div>
                </div>
                {inviteResult.invites.length > 0 && (
                  <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                    {inviteResult.invites.map((invite) => (
                      <div key={invite.id} className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-3">
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-white">{invite.email}</p>
                          <p className={`mt-0.5 text-xs ${invite.send_status === 'sent' ? 'text-green-300' : 'text-amber-300'}`}>
                            {t(`adminBrands.inviteStatus_${invite.send_status}`)}
                          </p>
                        </div>
                        {invite.invite_url && (
                          <button
                            type="button"
                            onClick={() => navigator.clipboard.writeText(invite.invite_url || '')}
                            className="rounded-lg bg-white/10 p-2 text-gray-300 transition-all hover:bg-white/20"
                            title={t('adminBrands.inviteCopy')}
                          >
                            <Copy className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex justify-end">
                  <button type="button" onClick={closeInvite} className="px-5 py-2.5 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-all">
                    {t('adminBrands.inviteClose')}
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={submitInvitePreview} className="space-y-4 overflow-y-auto p-6">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">{t('adminBrands.inviteEmail')}</label>
                  <textarea
                    required
                    rows={4}
                    value={inviteRecipients}
                    onChange={(e) => {
                      setInviteRecipients(e.target.value);
                      setInvitePreview(null);
                    }}
                    placeholder={t('adminBrands.inviteEmailsPlaceholder')}
                    className="w-full resize-y rounded-lg border border-white/20 bg-white/5 px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                  <p className="mt-1.5 text-xs text-gray-500">{t('adminBrands.inviteEmailsHint')}</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">{t('adminBrands.inviteBrandName')}</label>
                  <div className="relative">
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
                      <input
                        type="text"
                        required
                        value={inviteBrandName}
                        onFocus={() => setInviteBrandFocused(true)}
                        onBlur={() => setInviteBrandFocused(false)}
                        onChange={(e) => {
                          setInviteBrandName(e.target.value);
                          setInviteBrandId(null);
                          setInvitePreview(null);
                        }}
                        placeholder={t('adminBrands.inviteBrandNamePlaceholder')}
                        className="w-full rounded-lg border border-white/20 bg-white/5 py-2 pl-10 pr-4 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                      />
                    </div>

                    {inviteBrandFocused && (inviteBrandsLoading || inviteBrandMatches.length > 0) && (
                      <div className="absolute z-20 mt-2 max-h-56 w-full overflow-y-auto rounded-xl border border-white/15 bg-gray-950/95 p-1.5 shadow-2xl backdrop-blur-xl">
                        {inviteBrandsLoading && inviteBrandMatches.length === 0 ? (
                          <div className="flex items-center gap-2 px-3 py-3 text-sm text-gray-400">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            {t('adminBrands.inviteBrandSearching')}
                          </div>
                        ) : inviteBrandMatches.map((brand) => (
                          <button
                            key={brand.id}
                            type="button"
                            onMouseDown={(event) => event.preventDefault()}
                            onClick={() => {
                              setInviteBrandId(brand.id);
                              setInviteBrandName(brand.name);
                              setInviteBrandFocused(false);
                              setInvitePreview(null);
                            }}
                            className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-white/10"
                          >
                            <span className="min-w-0">
                              <span className="block truncate text-sm font-medium text-white">{brand.name}</span>
                              <span className="block truncate text-xs text-gray-500">/{brand.slug}</span>
                            </span>
                            <span className={`shrink-0 rounded-full px-2 py-1 text-[11px] font-medium ${brand.verified ? 'bg-green-500/15 text-green-300' : 'bg-amber-500/15 text-amber-300'}`}>
                              {brand.verified ? t('adminBrands.verified') : t('adminBrands.unverified')}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {inviteBrandName.trim() && (
                    <div className={`mt-2 flex items-start gap-2 rounded-lg border px-3 py-2 text-xs ${selectedInviteBrand || exactInviteBrand ? 'border-cyan-400/20 bg-cyan-400/10 text-cyan-200' : 'border-purple-400/20 bg-purple-400/10 text-purple-200'}`}>
                      {selectedInviteBrand || exactInviteBrand ? <Building2 className="mt-0.5 h-3.5 w-3.5 shrink-0" /> : <Plus className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
                      <span>
                        {selectedInviteBrand || exactInviteBrand
                          ? t('adminBrands.inviteExistingBrandHint')
                          : t('adminBrands.inviteNewBrandHint')}
                      </span>
                    </div>
                  )}
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">{t('adminBrands.inviteSender')}</label>
                  <select
                    value={inviteSenderProfile}
                    onChange={(e) => {
                      setInviteSenderProfile(e.target.value as 'partnerships' | 'pr' | 'transactional');
                      setInvitePreview(null);
                    }}
                    className="w-full rounded-lg border border-white/20 bg-gray-900 px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                  >
                    <option value="partnerships">{t('adminBrands.inviteSenderPartnerships')}</option>
                    <option value="pr">{t('adminBrands.inviteSenderPr')}</option>
                    <option value="transactional">{t('adminBrands.inviteSenderTransactional')}</option>
                  </select>
                </div>
                {invitePreview && (
                  <div className="space-y-3 rounded-xl border border-white/15 bg-black/20 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-medium text-white">{t('adminBrands.invitePreviewTitle')}</span>
                      <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${invitePreview.limit_exceeded ? 'bg-red-500/15 text-red-300' : 'bg-green-500/15 text-green-300'}`}>
                        {t('adminBrands.invitePreviewReady', { count: invitePreview.send_emails.length })}
                      </span>
                    </div>
                    {invitePreview.limit_exceeded && (
                      <p className="text-sm text-red-300">
                        {t('adminBrands.invitePreviewLimit', { count: invitePreview.max_recipients })}
                      </p>
                    )}
                    {invitePreview.invalid.length > 0 && (
                      <div>
                        <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-red-300">
                          {t('adminBrands.invitePreviewInvalid', { count: invitePreview.invalid.length })}
                        </p>
                        <div className="max-h-28 space-y-1 overflow-y-auto text-xs text-gray-300">
                          {invitePreview.invalid.map((item, index) => (
                            <p key={`${item.value}-${index}`}>
                              <span className="text-red-200">{item.value}</span>
                              {' · '}
                              {t(`adminBrands.inviteIssue_${item.code}`, { suggestion: item.suggestion || '' })}
                            </p>
                          ))}
                        </div>
                      </div>
                    )}
                    {invitePreview.duplicates.length > 0 && (
                      <p className="text-xs text-amber-200">
                        {t('adminBrands.invitePreviewDuplicates', { count: invitePreview.duplicates.length })}
                      </p>
                    )}
                    {invitePreview.already_invited.length > 0 && (
                      <p className="text-xs text-cyan-200">
                        {t('adminBrands.invitePreviewAlreadyInvited', { count: invitePreview.already_invited.length })}
                      </p>
                    )}
                    {invitePreview.confirmation_token && (
                      <p className="text-xs leading-relaxed text-gray-400">
                        {t('adminBrands.invitePreviewConfirmation')}
                      </p>
                    )}
                  </div>
                )}
                {inviteError && <p className="text-red-400 text-sm">{inviteError}</p>}
                <div className="flex flex-wrap justify-end gap-3">
                  <button type="button" onClick={closeInvite} className="px-5 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all">
                    {t('adminBrands.inviteCancel')}
                  </button>
                  <button
                    type="submit"
                    disabled={inviteSubmitting || !inviteRecipients.trim() || !inviteBrandName.trim()}
                    className="flex items-center gap-2 rounded-xl bg-white/10 px-5 py-2.5 text-white transition-all hover:bg-white/20 disabled:opacity-50"
                  >
                    {inviteSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                    {t(invitePreview ? 'adminBrands.invitePreviewAgain' : 'adminBrands.invitePreviewSubmit')}
                  </button>
                  {invitePreview?.confirmation_token && (
                    <button
                      type="button"
                      onClick={confirmInviteBatch}
                      disabled={inviteSubmitting || invitePreview.send_emails.length === 0 || invitePreview.limit_exceeded}
                      className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 px-5 py-2.5 text-white transition-all hover:from-purple-700 hover:to-pink-700 disabled:opacity-50"
                    >
                      {inviteSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                      {t('adminBrands.inviteSubmitCount', { count: invitePreview.send_emails.length })}
                    </button>
                  )}
                </div>
              </form>
            )}
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}


