/** Компонент для управления обратной связью от пользователей */

import { useState } from 'react';
import { ModalOverlay } from '../ModalOverlay';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { MessageCircle, Eye, Send, XCircle, Bug, Lightbulb, HelpCircle, MessageSquare, Filter, Search, Trash2 } from 'lucide-react';
import { adminFeedbackAPI } from '../../api/client';
import type { Feedback, FeedbackType, FeedbackStatus } from '../../types/api';
import { useTranslation } from 'react-i18next';
import { toast } from '../Toast';
import { ConfirmDeleteModal } from '../ConfirmDeleteModal';
import { translateApiError } from '../../utils/translateApiError';
import { createIdempotencyKey } from '../../utils/idempotencyKey';
import type { AxiosError } from 'axios';

export function AdminFeedback() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedStatus, setSelectedStatus] = useState<FeedbackStatus | 'all'>('all');
  const [selectedType, setSelectedType] = useState<FeedbackType | 'all'>('all');
  const [selectedFeedback, setSelectedFeedback] = useState<Feedback | null>(null);
  const [page, setPage] = useState(1);
  const [adminResponse, setAdminResponse] = useState('');
  const [replyIdempotencyKey, setReplyIdempotencyKey] = useState(createIdempotencyKey);
  const [responseStatus, setResponseStatus] = useState<FeedbackStatus>('in_progress');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Загрузка обратной связи
  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-feedback', selectedStatus, selectedType, page, searchQuery],
    queryFn: () => adminFeedbackAPI.list({
      page,
      size: 20,
      status: selectedStatus === 'all' ? undefined : selectedStatus,
      type: selectedType === 'all' ? undefined : selectedType,
    }),
  });

  const selectedFeedbackQuery = useQuery({
    queryKey: ['admin-feedback-detail', selectedFeedback?.id],
    queryFn: () => adminFeedbackAPI.get(selectedFeedback!.id),
    enabled: selectedFeedback !== null,
  });

  // Обновление обратной связи (ответ админа)
  const updateMutation = useMutation({
    mutationFn: ({
      id,
      status,
      response,
      idempotencyKey,
    }: {
      id: number;
      status?: FeedbackStatus;
      response?: string;
      idempotencyKey?: string;
    }) =>
      adminFeedbackAPI.update(id, {
        status: status || undefined,
        admin_response: response || undefined,
        reply_idempotency_key: response ? idempotencyKey : undefined,
      }),
    onSuccess: (updatedFeedback) => {
      queryClient.invalidateQueries({ queryKey: ['admin-feedback'] });
      queryClient.setQueryData(
        ['admin-feedback-detail', updatedFeedback.id],
        updatedFeedback,
      );
      setSelectedFeedback(updatedFeedback);
      setAdminResponse('');
      setReplyIdempotencyKey(createIdempotencyKey());
      setResponseStatus(updatedFeedback.status);
      toast.success(t('adminFeedback.replySent'));
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, error?.response?.data?.detail, t('adminFeedback.updateError')));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => adminFeedbackAPI.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-feedback'] });
      setSelectedFeedback(null);
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, error?.response?.data?.detail, t('adminFeedback.deleteError')));
    },
  });

  const handleResponse = (id: number) => {
    if (!adminResponse.trim()) {
      toast.error(t('adminFeedback.alert_enter_response'));
      return;
    }
    updateMutation.mutate({
      id,
      status: responseStatus,
      response: adminResponse,
      idempotencyKey: replyIdempotencyKey,
    });
  };

  const formatDate = (value: string) =>
    new Intl.DateTimeFormat(i18n.resolvedLanguage || i18n.language, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));

  const getStatusBadge = (status: FeedbackStatus) => {
    switch (status) {
      case 'open':
        return <span className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-400 text-xs font-semibold">{t('adminFeedback.filter_open')}</span>;
      case 'in_progress':
        return <span className="px-2 py-1 rounded bg-blue-500/20 text-blue-400 text-xs font-semibold">{t('adminFeedback.filter_in_progress')}</span>;
      case 'resolved':
        return <span className="px-2 py-1 rounded bg-green-500/20 text-green-400 text-xs font-semibold">{t('adminFeedback.filter_resolved')}</span>;
      case 'closed':
        return <span className="px-2 py-1 rounded bg-gray-500/20 text-gray-400 text-xs font-semibold">{t('adminFeedback.filter_closed')}</span>;
    }
  };

  const getTypeIcon = (type: FeedbackType) => {
    switch (type) {
      case 'bug':
        return Bug;
      case 'feature':
        return Lightbulb;
      case 'question':
        return HelpCircle;
      case 'other':
        return MessageSquare;
    }
  };

  const getTypeLabel = (type: FeedbackType) => {
    switch (type) {
      case 'bug':
        return t('adminFeedback.filter_bug');
      case 'feature':
        return t('adminFeedback.filter_feature');
      case 'question':
        return t('adminFeedback.filter_question');
      case 'other':
        return t('adminFeedback.filter_other');
    }
  };

  const feedbackItems = data?.items || [];
  const total = data?.total || 0;
  const pages = data?.pages || 0;
  const selectedFeedbackView = selectedFeedbackQuery.data ?? selectedFeedback;
  const threadMessages = selectedFeedbackQuery.data?.messages ?? (
    selectedFeedback
      ? [
          {
            id: `initial-${selectedFeedback.id}`,
            author_type: 'user' as const,
            message: selectedFeedback.message,
            created_at: selectedFeedback.created_at,
          },
          ...(selectedFeedback.admin_response
            ? [{
                id: `legacy-admin-${selectedFeedback.id}`,
                author_type: 'admin' as const,
                message: selectedFeedback.admin_response,
                created_at: selectedFeedback.admin_response_at ?? selectedFeedback.updated_at,
              }]
            : []),
        ]
      : []
  );

  // Фильтруем по поисковому запросу (если есть)
  const filteredItems = searchQuery
    ? feedbackItems.filter(
        (item) =>
          item.subject.toLowerCase().includes(searchQuery.toLowerCase()) ||
          item.message.toLowerCase().includes(searchQuery.toLowerCase()) ||
          item.email?.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : feedbackItems;

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">{t('adminFeedback.loading')}</div>;
  }

  if (error) {
    return <div className="text-center py-12 text-red-400">{t('adminFeedback.error')}</div>;
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-2">
          <MessageCircle className="w-6 h-6 text-purple-400" />
          {t('adminFeedback.title')}
        </h2>
        <p className="text-gray-300 text-sm mb-4">
          {t('adminFeedback.description')}
        </p>

        {/* Фильтры */}
        <div className="flex flex-wrap gap-4 mb-4">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-400" />
            <select
              value={selectedStatus}
              onChange={(e) => {
                setSelectedStatus(e.target.value as FeedbackStatus | 'all');
                setPage(1);
              }}
              className="px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="all">{t('adminFeedback.filter_all_statuses')}</option>
              <option value="open">{t('adminFeedback.filter_open')}</option>
              <option value="in_progress">{t('adminFeedback.filter_in_progress')}</option>
              <option value="resolved">{t('adminFeedback.filter_resolved')}</option>
              <option value="closed">{t('adminFeedback.filter_closed')}</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <select
              value={selectedType}
              onChange={(e) => {
                setSelectedType(e.target.value as FeedbackType | 'all');
                setPage(1);
              }}
              className="px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="all">{t('adminFeedback.filter_all_types')}</option>
              <option value="bug">{t('adminFeedback.filter_bug')}</option>
              <option value="feature">{t('adminFeedback.filter_feature')}</option>
              <option value="question">{t('adminFeedback.filter_question')}</option>
              <option value="other">{t('adminFeedback.filter_other')}</option>
            </select>
          </div>

          <div className="flex-1 min-w-[200px] relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('adminFeedback.search_placeholder')}
              className="w-full pl-10 pr-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>
        </div>

        <div className="text-sm text-gray-400">
          {t('adminFeedback.total_messages', { count: total })}
          {selectedStatus !== 'all' && ` • ${t('adminFeedback.status_label')}${getStatusBadge(selectedStatus)}`}
          {selectedType !== 'all' && ` • ${t('adminFeedback.type_label')}${getTypeLabel(selectedType)}`}
        </div>
      </div>

      {/* Список обратной связи */}
      {filteredItems.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          {searchQuery ? t('adminFeedback.no_feedback_found') : t('adminFeedback.no_feedback_yet')}
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {filteredItems.map((feedback) => {
              const TypeIcon = getTypeIcon(feedback.type);
              return (
                <div
                  key={feedback.id}
                  className="bg-white/5 border border-white/10 rounded-lg p-4 hover:bg-white/10 transition-all cursor-pointer"
                  onClick={() => {
                    setSelectedFeedback(feedback);
                    setAdminResponse('');
                    setReplyIdempotencyKey(createIdempotencyKey());
                    setResponseStatus('in_progress');
                  }}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <TypeIcon className="w-4 h-4 text-gray-400" />
                        <span className="text-xs text-gray-400">{getTypeLabel(feedback.type)}</span>
                        {getStatusBadge(feedback.status)}
                        {feedback.user_id ? (
                          <span className="text-xs text-gray-400">• {t('adminFeedback.user_id', { id: feedback.user_id })}</span>
                        ) : (
                          <span className="text-xs text-gray-400">• {t('adminFeedback.anonymous')}</span>
                        )}
                      </div>
                      <h3 className="text-white font-medium mb-1">{feedback.subject}</h3>
                      <p className="text-gray-400 text-sm line-clamp-2">{feedback.message}</p>
                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                        <span>{formatDate(feedback.created_at)}</span>
                        {feedback.email && <span>{t('adminFeedback.email', { email: feedback.email })}</span>}
                        {feedback.admin_response && (
                          <span className="text-green-400">{t('adminFeedback.responded')}</span>
                        )}
                      </div>
                    </div>
                    <Eye className="w-5 h-5 text-gray-400 flex-shrink-0" />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Пагинация */}
          {pages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-6">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 rounded-lg border border-white/20 text-sm text-gray-300 hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t('adminFeedback.pagination_back')}
              </button>
              <span className="text-sm text-gray-400">
                {t('adminFeedback.pagination_page_info', { page: page, pages: pages })}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(pages, p + 1))}
                disabled={page >= pages}
                className="px-3 py-1 rounded-lg border border-white/20 text-sm text-gray-300 hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t('adminFeedback.pagination_forward')}
              </button>
            </div>
          )}
        </>
      )}

      {/* Модалка просмотра и ответа */}
      {selectedFeedbackView && (
        <ModalOverlay onClose={() => { setSelectedFeedback(null); setAdminResponse(''); }} className="!bg-black/60">
              <div
                className="bg-gradient-to-br from-gray-900 to-gray-800 rounded-2xl shadow-2xl border border-white/20 max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col"
                onClick={(e) => e.stopPropagation()}
              >
                {/* Header */}
                <div className="flex items-start justify-between gap-4 px-6 pt-6 pb-4 border-b border-white/10">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      {(() => {
                        const TypeIcon = getTypeIcon(selectedFeedbackView.type);
                        return <TypeIcon className="w-5 h-5 text-purple-400" />;
                      })()}
                      <span className="text-sm text-gray-400">{getTypeLabel(selectedFeedbackView.type)}</span>
                      {getStatusBadge(selectedFeedbackView.status)}
                    </div>
                    <h2 className="text-2xl font-semibold text-white">{selectedFeedbackView.subject}</h2>
                    <div className="flex items-center gap-4 mt-2 text-sm text-gray-400">
                      <span>{formatDate(selectedFeedbackView.created_at)}</span>
                      {selectedFeedbackView.user_id ? (
                        <span>{t('adminFeedback.user_id', { id: selectedFeedbackView.user_id })}</span>
                      ) : (
                        <span>{t('adminFeedback.anonymous')} • {selectedFeedbackView.email}</span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      setSelectedFeedback(null);
                      setAdminResponse('');
                    }}
                    className="text-gray-400 hover:text-white transition-colors p-2 -mt-2 -mr-2"
                  >
                    <XCircle className="w-5 h-5" />
                  </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 custom-scrollbar">
                  <div>
                    <h3 className="mb-3 text-sm font-medium text-gray-300">
                      {t('adminFeedback.conversation')}
                    </h3>
                    <div className="space-y-3">
                      {threadMessages.map((threadMessage) => {
                        const fromAdmin = threadMessage.author_type === 'admin';
                        return (
                          <div
                            key={threadMessage.id}
                            className={`flex ${fromAdmin ? 'justify-end' : 'justify-start'}`}
                          >
                            <div className="max-w-[85%]">
                              <div
                                className={`mb-1 text-xs ${
                                  fromAdmin ? 'text-right text-purple-300' : 'text-cyan-300'
                                }`}
                              >
                                {fromAdmin
                                  ? t('adminFeedback.you')
                                  : t('adminFeedback.user')}
                                {' · '}
                                {formatDate(threadMessage.created_at)}
                              </div>
                              <div
                                className={`whitespace-pre-wrap break-words rounded-xl border p-3 text-sm leading-6 text-gray-200 ${
                                  fromAdmin
                                    ? 'rounded-tr-sm border-purple-400/25 bg-purple-500/10'
                                    : 'rounded-tl-sm border-cyan-400/20 bg-cyan-500/10'
                                }`}
                              >
                                {threadMessage.message}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Форма ответа */}
                  <div>
                    <h3 className="text-sm font-medium text-gray-300 mb-2">{t('adminFeedback.modal_response_placeholder')}</h3>
                    <textarea
                      value={adminResponse}
                      onChange={(e) => setAdminResponse(e.target.value)}
                      rows={6}
                      placeholder={t('adminFeedback.modal_response_placeholder')}
                      className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none custom-scrollbar"
                    />
                  </div>

                  {/* Статус */}
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">
                      {t('adminFeedback.modal_change_status')}
                    </label>
                    <select
                      value={responseStatus}
                      onChange={(e) => setResponseStatus(e.target.value as FeedbackStatus)}
                      className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                    >
                      <option value="open">{t('adminFeedback.filter_open')}</option>
                      <option value="in_progress">{t('adminFeedback.filter_in_progress')}</option>
                      <option value="resolved">{t('adminFeedback.filter_resolved')}</option>
                      <option value="closed">{t('adminFeedback.filter_closed')}</option>
                    </select>
                    <p className="mt-2 text-xs leading-5 text-gray-400">
                      {t('adminFeedback.statusReplyHint')}
                    </p>
                  </div>
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between px-6 py-4 border-t border-white/10">
                  <button
                    onClick={() => setShowDeleteConfirm(true)}
                    disabled={deleteMutation.isPending}
                    className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-medium transition-all disabled:opacity-50 flex items-center gap-2"
                  >
                    <Trash2 className="w-4 h-4" />
                    {t('adminFeedback.deleteButton')}
                  </button>
                  <div className="flex items-center gap-3">
                  <button
                    onClick={() => {
                      setSelectedFeedback(null);
                      setAdminResponse('');
                    }}
                    className="px-4 py-2 rounded-lg border border-white/20 text-sm text-gray-300 hover:bg-white/10 transition-all"
                  >
                    {t('adminFeedback.modal_close_button')}
                  </button>
                  <button
                    onClick={() => handleResponse(selectedFeedbackView.id)}
                    disabled={!adminResponse.trim() || updateMutation.isPending}
                    className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  >
                    {updateMutation.isPending ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        {t('adminFeedback.modal_saving_button')}
                      </>
                    ) : (
                      <>
                        <Send className="w-4 h-4" />
                        {t('adminFeedback.modal_save_button')}
                      </>
                    )}
                  </button>
                  </div>
                </div>
              </div>
        </ModalOverlay>
      )}

      <ConfirmDeleteModal
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={() => {
          if (selectedFeedback) deleteMutation.mutate(selectedFeedback.id);
          setShowDeleteConfirm(false);
        }}
        message={t('adminFeedback.confirmDelete')}
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}


