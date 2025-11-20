/** Компонент для управления обратной связью от пользователей */

import { useState } from 'react';
import { createPortal } from 'react-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { MessageCircle, Eye, Send, CheckCircle, Clock, XCircle, AlertCircle, Bug, Lightbulb, HelpCircle, MessageSquare, Filter, Search } from 'lucide-react';
import { adminFeedbackAPI } from '../../api/client';
import type { Feedback, FeedbackType, FeedbackStatus } from '../../types/api';
import { useHeaderVisible } from '../../hooks/useHeaderVisible';

export function AdminFeedback() {
  const isHeaderVisible = useHeaderVisible();
  const queryClient = useQueryClient();
  const [selectedStatus, setSelectedStatus] = useState<FeedbackStatus | 'all'>('all');
  const [selectedType, setSelectedType] = useState<FeedbackType | 'all'>('all');
  const [selectedFeedback, setSelectedFeedback] = useState<Feedback | null>(null);
  const [page, setPage] = useState(1);
  const [adminResponse, setAdminResponse] = useState('');
  const [responseStatus, setResponseStatus] = useState<FeedbackStatus>('resolved');
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

  // Обновление обратной связи (ответ админа)
  const updateMutation = useMutation({
    mutationFn: ({ id, status, response }: { id: number; status?: FeedbackStatus; response?: string }) =>
      adminFeedbackAPI.update(id, {
        status: status || undefined,
        admin_response: response || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-feedback'] });
      setSelectedFeedback(null);
      setAdminResponse('');
    },
  });

  const handleResponse = (id: number) => {
    if (!adminResponse.trim()) {
      alert('Введите ответ пользователю');
      return;
    }
    updateMutation.mutate({ id, status: responseStatus, response: adminResponse });
  };

  const getStatusBadge = (status: FeedbackStatus) => {
    switch (status) {
      case 'open':
        return <span className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-400 text-xs font-semibold">Открыто</span>;
      case 'in_progress':
        return <span className="px-2 py-1 rounded bg-blue-500/20 text-blue-400 text-xs font-semibold">В работе</span>;
      case 'resolved':
        return <span className="px-2 py-1 rounded bg-green-500/20 text-green-400 text-xs font-semibold">Решено</span>;
      case 'closed':
        return <span className="px-2 py-1 rounded bg-gray-500/20 text-gray-400 text-xs font-semibold">Закрыто</span>;
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
        return 'Ошибка';
      case 'feature':
        return 'Предложение';
      case 'question':
        return 'Вопрос';
      case 'other':
        return 'Другое';
    }
  };

  const feedbackItems = data?.items || [];
  const total = data?.total || 0;
  const pages = data?.pages || 0;

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
    return <div className="text-center py-12 text-gray-400">Загрузка обратной связи...</div>;
  }

  if (error) {
    return <div className="text-center py-12 text-red-400">Ошибка загрузки обратной связи</div>;
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-2">
          <MessageCircle className="w-6 h-6 text-purple-400" />
          Обратная связь от пользователей
        </h2>
        <p className="text-gray-300 text-sm mb-4">
          Все сообщения от пользователей сохраняются здесь. Вы можете просматривать, отвечать и менять статус обращений.
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
              <option value="all">Все статусы</option>
              <option value="open">Открыто</option>
              <option value="in_progress">В работе</option>
              <option value="resolved">Решено</option>
              <option value="closed">Закрыто</option>
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
              <option value="all">Все типы</option>
              <option value="bug">Ошибки</option>
              <option value="feature">Предложения</option>
              <option value="question">Вопросы</option>
              <option value="other">Другое</option>
            </select>
          </div>

          <div className="flex-1 min-w-[200px] relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Поиск по теме, тексту или email..."
              className="w-full pl-10 pr-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>
        </div>

        <div className="text-sm text-gray-400">
          Всего сообщений: <span className="text-white font-semibold">{total}</span>
          {selectedStatus !== 'all' && ` • Статус: ${getStatusBadge(selectedStatus)}`}
          {selectedType !== 'all' && ` • Тип: ${getTypeLabel(selectedType)}`}
        </div>
      </div>

      {/* Список обратной связи */}
      {filteredItems.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          {searchQuery ? 'Ничего не найдено по вашему запросу' : 'Пока нет обратной связи'}
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
                  onClick={() => setSelectedFeedback(feedback)}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <TypeIcon className="w-4 h-4 text-gray-400" />
                        <span className="text-xs text-gray-400">{getTypeLabel(feedback.type)}</span>
                        {getStatusBadge(feedback.status)}
                        {feedback.user_id ? (
                          <span className="text-xs text-gray-400">• Пользователь #{feedback.user_id}</span>
                        ) : (
                          <span className="text-xs text-gray-400">• Анонимно</span>
                        )}
                      </div>
                      <h3 className="text-white font-medium mb-1">{feedback.subject}</h3>
                      <p className="text-gray-400 text-sm line-clamp-2">{feedback.message}</p>
                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                        <span>{new Date(feedback.created_at).toLocaleString('ru-RU')}</span>
                        {feedback.email && <span>Email: {feedback.email}</span>}
                        {feedback.admin_response && (
                          <span className="text-green-400">✓ Отвечено</span>
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
                Назад
              </button>
              <span className="text-sm text-gray-400">
                Страница {page} из {pages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(pages, p + 1))}
                disabled={page >= pages}
                className="px-3 py-1 rounded-lg border border-white/20 text-sm text-gray-300 hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Вперед
              </button>
            </div>
          )}
        </>
      )}

      {/* Модалка просмотра и ответа */}
      {selectedFeedback &&
        createPortal(
          <div
            className={`fixed inset-0 z-[200] ${isHeaderVisible ? 'pt-[88px]' : ''}`}
            onClick={() => {
              setSelectedFeedback(null);
              setAdminResponse('');
            }}
          >
            <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
            <div
              className={`fixed inset-0 flex items-center justify-center pointer-events-none p-4 ${isHeaderVisible ? 'pt-[88px]' : ''}`}
            >
              <div
                className={`bg-gradient-to-br from-gray-900 to-gray-800 rounded-2xl shadow-2xl border border-white/20 max-w-3xl w-full ${isHeaderVisible ? 'max-h-[calc(100vh-100px)]' : 'max-h-[90vh]'} overflow-hidden flex flex-col pointer-events-auto`}
                onClick={(e) => e.stopPropagation()}
              >
                {/* Header */}
                <div className="flex items-start justify-between gap-4 px-6 pt-6 pb-4 border-b border-white/10">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      {(() => {
                        const TypeIcon = getTypeIcon(selectedFeedback.type);
                        return <TypeIcon className="w-5 h-5 text-purple-400" />;
                      })()}
                      <span className="text-sm text-gray-400">{getTypeLabel(selectedFeedback.type)}</span>
                      {getStatusBadge(selectedFeedback.status)}
                    </div>
                    <h2 className="text-2xl font-semibold text-white">{selectedFeedback.subject}</h2>
                    <div className="flex items-center gap-4 mt-2 text-sm text-gray-400">
                      <span>{new Date(selectedFeedback.created_at).toLocaleString('ru-RU')}</span>
                      {selectedFeedback.user_id ? (
                        <span>Пользователь #{selectedFeedback.user_id}</span>
                      ) : (
                        <span>Анонимно • {selectedFeedback.email}</span>
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
                  {/* Сообщение пользователя */}
                  <div>
                    <h3 className="text-sm font-medium text-gray-300 mb-2">Сообщение пользователя:</h3>
                    <div className="bg-white/5 border border-white/10 rounded-lg p-4 text-gray-300 whitespace-pre-wrap">
                      {selectedFeedback.message}
                    </div>
                  </div>

                  {/* Ответ админа (если есть) */}
                  {selectedFeedback.admin_response && (
                    <div>
                      <h3 className="text-sm font-medium text-gray-300 mb-2">
                        Ваш ответ ({selectedFeedback.admin_response_at && new Date(selectedFeedback.admin_response_at).toLocaleString('ru-RU')}):
                      </h3>
                      <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4 text-gray-300 whitespace-pre-wrap">
                        {selectedFeedback.admin_response}
                      </div>
                    </div>
                  )}

                  {/* Форма ответа */}
                  <div>
                    <h3 className="text-sm font-medium text-gray-300 mb-2">Ответ пользователю:</h3>
                    <textarea
                      value={adminResponse}
                      onChange={(e) => setAdminResponse(e.target.value)}
                      rows={6}
                      placeholder="Введите ответ пользователю..."
                      className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none custom-scrollbar"
                    />
                  </div>

                  {/* Статус */}
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">
                      Изменить статус:
                    </label>
                    <select
                      value={responseStatus}
                      onChange={(e) => setResponseStatus(e.target.value as FeedbackStatus)}
                      className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                    >
                      <option value="open">Открыто</option>
                      <option value="in_progress">В работе</option>
                      <option value="resolved">Решено</option>
                      <option value="closed">Закрыто</option>
                    </select>
                  </div>
                </div>

                {/* Footer */}
                <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-white/10">
                  <button
                    onClick={() => {
                      setSelectedFeedback(null);
                      setAdminResponse('');
                    }}
                    className="px-4 py-2 rounded-lg border border-white/20 text-sm text-gray-300 hover:bg-white/10 transition-all"
                  >
                    Закрыть
                  </button>
                  <button
                    onClick={() => handleResponse(selectedFeedback.id)}
                    disabled={!adminResponse.trim() || updateMutation.isPending}
                    className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  >
                    {updateMutation.isPending ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Сохранение...
                      </>
                    ) : (
                      <>
                        <Send className="w-4 h-4" />
                        Сохранить ответ
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}


