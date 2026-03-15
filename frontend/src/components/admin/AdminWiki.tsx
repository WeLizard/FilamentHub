/** Admin Wiki management component */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ModalOverlay } from '../ModalOverlay';
import {
  BookOpen, FolderOpen, Settings, Plus, Edit, Trash2, Download,
  RefreshCw, Upload, Loader2, X, Save, Eye,
  CheckCircle, XCircle, AlertCircle, FileText,
} from 'lucide-react';
import { wikiAPI, adminAPI } from '../../api/client';
import type { WikiArticle, WikiArticleSummary, WikiCategory } from '../../types/api';

type WikiSection = 'articles' | 'categories' | 'operations';

// ============================================================================
// Article Edit Modal
// ============================================================================

function ArticleModal({
  article,
  categories,
  onClose,
  onSave,
  isSaving,
  t,
}: {
  article: Partial<WikiArticle> | null;
  categories: WikiCategory[];
  onClose: () => void;
  onSave: (data: any) => void;
  isSaving: boolean;
  t: (key: string) => string;
}) {
  const isNew = !article?.id;
  const [title, setTitle] = useState(article?.title || '');
  const [slug, setSlug] = useState(article?.slug || '');
  const [summary, setSummary] = useState(article?.summary || '');
  const [content, setContent] = useState(article?.content || '');
  const [categoryId, setCategoryId] = useState(article?.category_id || (categories[0]?.id || 0));
  const [tags, setTags] = useState((article?.tags || []).join(', '));
  const [published, setPublished] = useState(article?.published ?? true);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const tagsArr = tags.split(',').map(t => t.trim()).filter(Boolean);
    const data: any = {
      title,
      slug,
      summary,
      content,
      category_id: categoryId,
      tags: tagsArr.length > 0 ? tagsArr : null,
      published,
    };
    if (article?.id) {
      data.id = article.id;
    }
    onSave(data);
  };

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-gray-900 border border-white/20 rounded-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-xl font-bold text-white">
            {isNew ? t('adminWiki.createArticle') : t('adminWiki.editArticle')}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">{t('adminWiki.fieldTitle')}</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">{t('adminWiki.fieldSlug')}</label>
              <input
                type="text"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                required
                pattern="[-a-z0-9]+"
                className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">{t('adminWiki.fieldCategory')}</label>
              <select
                value={categoryId}
                onChange={(e) => setCategoryId(Number(e.target.value))}
                className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                {categories.map((cat) => (
                  <option key={cat.id} value={cat.id} className="bg-gray-900">
                    {cat.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">{t('adminWiki.fieldTags')}</label>
              <input
                type="text"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="tag1, tag2, tag3"
                className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">{t('adminWiki.fieldSummary')}</label>
            <textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              required
              rows={2}
              className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-y"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">{t('adminWiki.fieldContent')}</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              required
              rows={12}
              className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-y font-mono text-sm"
            />
          </div>

          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={published}
                onChange={(e) => setPublished(e.target.checked)}
                className="rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
              />
              {t('adminWiki.statusPublished')}
            </label>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-white/10 text-gray-300 rounded-lg hover:bg-white/20 transition-colors"
            >
              {t('adminWiki.cancel')}
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {t('adminWiki.save')}
            </button>
          </div>
        </form>
      </div>
    </ModalOverlay>
  );
}

// ============================================================================
// Category Edit Modal
// ============================================================================

function CategoryModal({
  category,
  onClose,
  onSave,
  isSaving,
  t,
}: {
  category: Partial<WikiCategory> | null;
  onClose: () => void;
  onSave: (data: any) => void;
  isSaving: boolean;
  t: (key: string) => string;
}) {
  const isNew = !category?.id;
  const [name, setName] = useState(category?.name || '');
  const [slug, setSlug] = useState(category?.slug || '');
  const [description, setDescription] = useState(category?.description || '');
  const [icon, setIcon] = useState(category?.icon || '');
  const [order, setOrder] = useState(category?.order ?? 0);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const data: any = { name, slug, description, icon: icon || null, order };
    if (category?.id) {
      data.id = category.id;
    }
    onSave(data);
  };

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-gray-900 border border-white/20 rounded-2xl w-full max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-xl font-bold text-white">
            {isNew ? t('adminWiki.createCategory') : t('adminWiki.editCategory')}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">{t('adminWiki.fieldName')}</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">{t('adminWiki.fieldSlug')}</label>
            <input
              type="text"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              required
              pattern="[-a-z0-9]+"
              className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">{t('adminWiki.fieldDescription')}</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
              rows={3}
              className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-purple-500 resize-y"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">{t('adminWiki.fieldIcon')}</label>
              <input
                type="text"
                value={icon}
                onChange={(e) => setIcon(e.target.value)}
                placeholder="📄"
                className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">{t('adminWiki.fieldOrder')}</label>
              <input
                type="number"
                value={order}
                onChange={(e) => setOrder(Number(e.target.value))}
                min={0}
                className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-white/10 text-gray-300 rounded-lg hover:bg-white/20 transition-colors"
            >
              {t('adminWiki.cancel')}
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {t('adminWiki.save')}
            </button>
          </div>
        </form>
      </div>
    </ModalOverlay>
  );
}

// ============================================================================
// Status Badge
// ============================================================================

function StatusBadge({ published, t }: { published: boolean; t: (key: string) => string }) {
  if (published) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/20 text-green-400">
        <CheckCircle className="w-3 h-3" />
        {t('adminWiki.statusPublished')}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-500/20 text-yellow-400">
      <AlertCircle className="w-3 h-3" />
      {t('adminWiki.statusDraft')}
    </span>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function AdminWiki() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [section, setSection] = useState<WikiSection>('articles');

  // Article state
  const [articlePage, setArticlePage] = useState(1);
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [editingArticle, setEditingArticle] = useState<Partial<WikiArticle> | null>(null);
  const [showArticleModal, setShowArticleModal] = useState(false);

  // Category state
  const [editingCategory, setEditingCategory] = useState<Partial<WikiCategory> | null>(null);
  const [showCategoryModal, setShowCategoryModal] = useState(false);

  // Operation results
  const [operationResult, setOperationResult] = useState<any>(null);

  // ==================== Queries ====================

  const { data: articlesData, isLoading: articlesLoading } = useQuery({
    queryKey: ['admin-wiki-articles', articlePage, categoryFilter, statusFilter],
    queryFn: () => wikiAPI.listArticles({
      page: articlePage,
      page_size: 20,
      category_slug: categoryFilter || undefined,
      published_only: statusFilter === 'published' ? true : statusFilter === 'draft' ? false : undefined,
    }),
    enabled: section === 'articles',
  });

  const { data: categoriesData, isLoading: categoriesLoading } = useQuery({
    queryKey: ['admin-wiki-categories'],
    queryFn: () => wikiAPI.listCategories({ page: 1, page_size: 100 }),
  });

  // ==================== Mutations ====================

  const createArticleMutation = useMutation({
    mutationFn: (data: any) => wikiAPI.createArticle(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-wiki-articles'] });
      queryClient.invalidateQueries({ queryKey: ['admin-wiki-categories'] });
      setShowArticleModal(false);
      setEditingArticle(null);
    },
  });

  const updateArticleMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => wikiAPI.updateArticle(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-wiki-articles'] });
      queryClient.invalidateQueries({ queryKey: ['admin-wiki-categories'] });
      setShowArticleModal(false);
      setEditingArticle(null);
    },
  });

  const deleteArticleMutation = useMutation({
    mutationFn: (id: number) => wikiAPI.deleteArticle(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-wiki-articles'] });
      queryClient.invalidateQueries({ queryKey: ['admin-wiki-categories'] });
    },
  });

  const createCategoryMutation = useMutation({
    mutationFn: (data: any) => wikiAPI.createCategory(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-wiki-categories'] });
      setShowCategoryModal(false);
      setEditingCategory(null);
    },
  });

  const updateCategoryMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => wikiAPI.updateCategory(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-wiki-categories'] });
      setShowCategoryModal(false);
      setEditingCategory(null);
    },
  });

  const deleteCategoryMutation = useMutation({
    mutationFn: (id: number) => wikiAPI.deleteCategory(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-wiki-categories'] });
    },
  });

  const syncMutation = useMutation({
    mutationFn: () => adminAPI.syncWiki(),
    onSuccess: (data) => {
      setOperationResult({ type: 'sync', ...data });
      queryClient.invalidateQueries({ queryKey: ['admin-wiki-articles'] });
      queryClient.invalidateQueries({ queryKey: ['admin-wiki-categories'] });
    },
    onError: () => {
      setOperationResult({ type: 'sync', success: false, message: t('adminWiki.operationError') });
    },
  });

  const exportMutation = useMutation({
    mutationFn: () => adminAPI.exportWiki(),
    onSuccess: (data) => {
      setOperationResult({ type: 'export', ...data });
    },
    onError: () => {
      setOperationResult({ type: 'export', success: false, message: t('adminWiki.operationError') });
    },
  });

  // ==================== Handlers ====================

  const handleSaveArticle = (data: any) => {
    const { id, ...rest } = data;
    if (id) {
      updateArticleMutation.mutate({ id, data: rest });
    } else {
      createArticleMutation.mutate(rest);
    }
  };

  const handleEditArticle = async (article: WikiArticleSummary) => {
    // Fetch full article with content
    try {
      const full = await wikiAPI.getArticle(article.slug);
      setEditingArticle(full);
      setShowArticleModal(true);
    } catch {
      // Fallback to summary data
      setEditingArticle(article as any);
      setShowArticleModal(true);
    }
  };

  const handleDeleteArticle = (id: number) => {
    if (confirm(t('adminWiki.confirmDelete'))) {
      deleteArticleMutation.mutate(id);
    }
  };

  const handleSaveCategory = (data: any) => {
    const { id, ...rest } = data;
    if (id) {
      updateCategoryMutation.mutate({ id, data: rest });
    } else {
      createCategoryMutation.mutate(rest);
    }
  };

  const handleDeleteCategory = (id: number) => {
    if (confirm(t('adminWiki.confirmDeleteCategory'))) {
      deleteCategoryMutation.mutate(id);
    }
  };

  const handleDownloadArticle = async (id: number) => {
    try {
      await adminAPI.exportArticle(id);
    } catch (err) {
      console.error('Failed to download article:', err);
    }
  };

  const categories = categoriesData?.items || [];
  const articles = articlesData?.items || [];
  const totalArticlePages = articlesData?.total_pages || 0;

  // ==================== Render ====================

  const sectionTabs = [
    { id: 'articles' as WikiSection, label: t('adminWiki.articles'), icon: FileText },
    { id: 'categories' as WikiSection, label: t('adminWiki.categories'), icon: FolderOpen },
    { id: 'operations' as WikiSection, label: t('adminWiki.operations'), icon: Settings },
  ];

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <BookOpen className="w-6 h-6 text-purple-400" />
          <h2 className="text-xl font-bold text-white">{t('adminWiki.title')}</h2>
        </div>
      </div>

      {/* Section tabs */}
      <div className="flex gap-2 mb-6">
        {sectionTabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setSection(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all text-sm ${
                section === tab.id
                  ? 'bg-purple-600 text-white'
                  : 'bg-white/5 text-gray-300 hover:bg-white/10'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ==================== Articles Section ==================== */}
      {section === 'articles' && (
        <div>
          {/* Filters & Actions */}
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <select
              value={categoryFilter}
              onChange={(e) => { setCategoryFilter(e.target.value); setArticlePage(1); }}
              className="bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="" className="bg-gray-900">{t('adminWiki.allCategories')}</option>
              {categories.map((cat) => (
                <option key={cat.slug} value={cat.slug} className="bg-gray-900">
                  {cat.icon} {cat.name}
                </option>
              ))}
            </select>

            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setArticlePage(1); }}
              className="bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="" className="bg-gray-900">{t('adminWiki.allStatuses')}</option>
              <option value="published" className="bg-gray-900">{t('adminWiki.statusPublished')}</option>
              <option value="draft" className="bg-gray-900">{t('adminWiki.statusDraft')}</option>
            </select>

            <div className="ml-auto">
              <button
                onClick={() => { setEditingArticle({}); setShowArticleModal(true); }}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm"
              >
                <Plus className="w-4 h-4" />
                {t('adminWiki.createArticle')}
              </button>
            </div>
          </div>

          {/* Articles Table */}
          {articlesLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-8 h-8 text-purple-400 animate-spin" />
            </div>
          ) : articles.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>{t('adminWiki.noArticles')}</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left py-3 px-3 text-gray-400 font-medium">{t('adminWiki.fieldTitle')}</th>
                    <th className="text-left py-3 px-3 text-gray-400 font-medium hidden md:table-cell">{t('adminWiki.fieldCategory')}</th>
                    <th className="text-left py-3 px-3 text-gray-400 font-medium">{t('adminWiki.fieldStatus')}</th>
                    <th className="text-right py-3 px-3 text-gray-400 font-medium hidden sm:table-cell">
                      <Eye className="w-4 h-4 inline" />
                    </th>
                    <th className="text-right py-3 px-3 text-gray-400 font-medium w-40"></th>
                  </tr>
                </thead>
                <tbody>
                  {articles.map((article) => {
                    const cat = categories.find(c => c.id === article.category_id);
                    return (
                      <tr key={article.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                        <td className="py-3 px-3">
                          <div className="text-white font-medium">{article.title}</div>
                          <div className="text-xs text-gray-500 mt-0.5">{article.slug}</div>
                        </td>
                        <td className="py-3 px-3 text-gray-300 hidden md:table-cell">
                          {cat ? (
                            <span>{cat.icon} {cat.name}</span>
                          ) : (
                            <span className="text-gray-500">—</span>
                          )}
                        </td>
                        <td className="py-3 px-3">
                          <StatusBadge published={article.published} t={t} />
                        </td>
                        <td className="py-3 px-3 text-right text-gray-400 hidden sm:table-cell">
                          {article.views}
                        </td>
                        <td className="py-3 px-3 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => handleEditArticle(article)}
                              className="p-1.5 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                              title={t('adminWiki.edit')}
                            >
                              <Edit className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleDownloadArticle(article.id)}
                              className="p-1.5 text-gray-400 hover:text-blue-400 hover:bg-blue-500/10 rounded-lg transition-colors"
                              title={t('adminWiki.download')}
                            >
                              <Download className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleDeleteArticle(article.id)}
                              disabled={deleteArticleMutation.isPending}
                              className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                              title={t('adminWiki.delete')}
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {totalArticlePages > 1 && (
            <div className="flex justify-center gap-2 mt-4">
              {Array.from({ length: totalArticlePages }, (_, i) => i + 1).map((p) => (
                <button
                  key={p}
                  onClick={() => setArticlePage(p)}
                  className={`px-3 py-1 rounded-lg text-sm transition-colors ${
                    articlePage === p
                      ? 'bg-purple-600 text-white'
                      : 'bg-white/5 text-gray-400 hover:bg-white/10'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ==================== Categories Section ==================== */}
      {section === 'categories' && (
        <div>
          <div className="flex justify-end mb-4">
            <button
              onClick={() => { setEditingCategory({}); setShowCategoryModal(true); }}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm"
            >
              <Plus className="w-4 h-4" />
              {t('adminWiki.createCategory')}
            </button>
          </div>

          {categoriesLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-8 h-8 text-purple-400 animate-spin" />
            </div>
          ) : categories.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <FolderOpen className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>{t('adminWiki.noCategories')}</p>
            </div>
          ) : (
            <div className="grid gap-3">
              {categories.map((cat) => (
                <div
                  key={cat.id}
                  className="flex items-center justify-between bg-white/5 border border-white/10 rounded-xl px-4 py-3 hover:bg-white/10 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{cat.icon || '📄'}</span>
                    <div>
                      <div className="text-white font-medium">{cat.name}</div>
                      <div className="text-xs text-gray-400">
                        {cat.slug} &middot; {cat.articles_count} {t('adminWiki.articlesCount')}
                      </div>
                      {cat.description && (
                        <div className="text-xs text-gray-500 mt-1 max-w-lg truncate">{cat.description}</div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => { setEditingCategory(cat); setShowCategoryModal(true); }}
                      className="p-1.5 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                      title={t('adminWiki.edit')}
                    >
                      <Edit className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDeleteCategory(cat.id)}
                      disabled={deleteCategoryMutation.isPending}
                      className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                      title={t('adminWiki.delete')}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ==================== Operations Section ==================== */}
      {section === 'operations' && (
        <div className="space-y-6">
          {/* Sync */}
          <div className="bg-white/5 border border-white/10 rounded-xl p-6">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <RefreshCw className="w-5 h-5 text-blue-400" />
                  {t('adminWiki.sync')}
                </h3>
                <p className="text-sm text-gray-400 mt-1">{t('adminWiki.syncDescription')}</p>
              </div>
              <button
                onClick={() => syncMutation.mutate()}
                disabled={syncMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
              >
                {syncMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <RefreshCw className="w-4 h-4" />
                )}
                {t('adminWiki.sync')}
              </button>
            </div>
          </div>

          {/* Export */}
          <div className="bg-white/5 border border-white/10 rounded-xl p-6">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Upload className="w-5 h-5 text-green-400" />
                  {t('adminWiki.export')}
                </h3>
                <p className="text-sm text-gray-400 mt-1">{t('adminWiki.exportDescription')}</p>
              </div>
              <button
                onClick={() => exportMutation.mutate()}
                disabled={exportMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50"
              >
                {exportMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Upload className="w-4 h-4" />
                )}
                {t('adminWiki.export')}
              </button>
            </div>
          </div>

          {/* Operation Result */}
          {operationResult && (
            <div className={`border rounded-xl p-6 ${
              operationResult.success
                ? 'bg-green-500/10 border-green-500/30'
                : 'bg-red-500/10 border-red-500/30'
            }`}>
              <div className="flex items-center gap-2 mb-3">
                {operationResult.success ? (
                  <CheckCircle className="w-5 h-5 text-green-400" />
                ) : (
                  <XCircle className="w-5 h-5 text-red-400" />
                )}
                <h3 className="text-lg font-semibold text-white">
                  {operationResult.type === 'sync' ? t('adminWiki.syncResult') : t('adminWiki.exportResult')}
                </h3>
                <button
                  onClick={() => setOperationResult(null)}
                  className="ml-auto text-gray-400 hover:text-white"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <p className="text-gray-300 mb-3">{operationResult.message}</p>

              {operationResult.type === 'sync' && operationResult.success && (
                <div className="flex flex-wrap gap-4 text-sm">
                  <span className="text-green-400">{operationResult.created} {t('adminWiki.created')}</span>
                  <span className="text-blue-400">{operationResult.updated} {t('adminWiki.updated')}</span>
                  <span className="text-gray-400">{operationResult.skipped} {t('adminWiki.skipped')}</span>
                  {operationResult.errors > 0 && (
                    <span className="text-red-400">{operationResult.errors} {t('adminWiki.errors')}</span>
                  )}
                </div>
              )}

              {operationResult.type === 'export' && operationResult.success && (
                <div className="flex flex-wrap gap-4 text-sm">
                  <span className="text-green-400">{operationResult.exported} {t('adminWiki.exported')}</span>
                  {operationResult.errors > 0 && (
                    <span className="text-red-400">{operationResult.errors} {t('adminWiki.errors')}</span>
                  )}
                </div>
              )}

              {/* Details */}
              {operationResult.details && operationResult.details.length > 0 && (
                <div className="mt-4 max-h-48 overflow-y-auto">
                  <table className="w-full text-xs">
                    <tbody>
                      {operationResult.details.map((d: any, i: number) => (
                        <tr key={i} className="border-b border-white/5">
                          <td className="py-1 px-2 text-gray-400">{d.file}</td>
                          <td className="py-1 px-2">
                            <span className={`${
                              d.status === 'created' || d.status === 'exported' ? 'text-green-400' :
                              d.status === 'updated' ? 'text-blue-400' :
                              d.status === 'skipped' ? 'text-gray-400' :
                              'text-red-400'
                            }`}>
                              {d.status}
                            </span>
                          </td>
                          <td className="py-1 px-2 text-gray-300">{d.title || d.reason || ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ==================== Modals ==================== */}
      {showArticleModal && (
        <ArticleModal
          article={editingArticle}
          categories={categories}
          onClose={() => { setShowArticleModal(false); setEditingArticle(null); }}
          onSave={handleSaveArticle}
          isSaving={createArticleMutation.isPending || updateArticleMutation.isPending}
          t={t}
        />
      )}

      {showCategoryModal && (
        <CategoryModal
          category={editingCategory}
          onClose={() => { setShowCategoryModal(false); setEditingCategory(null); }}
          onSave={handleSaveCategory}
          isSaving={createCategoryMutation.isPending || updateCategoryMutation.isPending}
          t={t}
        />
      )}
    </div>
  );
}
