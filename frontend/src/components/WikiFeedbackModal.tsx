/** Модальное окно для отзыва на wiki статью */

import { useState } from 'react';
import { X, Send, MessageSquare } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { wikiAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useHeaderVisible } from '../hooks/useHeaderVisible';

interface WikiFeedbackModalProps {
  isOpen: boolean;
  onClose: () => void;
  articleSlug: string;
  articleTitle: string;
}

export const WikiFeedbackModal: React.FC<WikiFeedbackModalProps> = ({
  isOpen,
  onClose,
  articleSlug,
  articleTitle,
}) => {
  const { user } = useAuth();
  const isHeaderVisible = useHeaderVisible();
  const queryClient = useQueryClient();

  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Мутация для создания отзыва
  const createFeedbackMutation = useMutation({
    mutationFn: (commentText: string) =>
      wikiAPI.createFeedback(articleSlug, {
        feedback_type: 'feedback',
        comment: commentText,
      }),
    onSuccess: () => {
      setSuccess(true);
      // Обновляем статистику
      queryClient.invalidateQueries({ queryKey: ['wiki-feedback-stats', articleSlug] });
      queryClient.invalidateQueries({ queryKey: ['wiki-feedback-list', articleSlug] });
      // Закрываем модалку через 2 секунды
      setTimeout(() => {
        setComment('');
        setSuccess(false);
        onClose();
      }, 2000);
    },
    onError: (err: any) => {
      console.error('Error creating feedback:', err);
      setError(
        err?.response?.data?.detail ||
          err?.message ||
          'Не удалось отправить отзыв. Попробуйте позже.'
      );
    },
  });

  // Показываем модалку только для авторизованных пользователей
  if (!isOpen) return null;

  // Если пользователь не авторизован, показываем сообщение
  if (!user) {
    return (
      <div
        className={`fixed inset-0 z-[100] ${isHeaderVisible ? 'pt-[72px] md:pt-[88px]' : ''}`}
        onClick={onClose}
      >
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
        <div
          className="fixed inset-0 flex items-center justify-center pointer-events-none p-4"
          style={{ top: isHeaderVisible ? '72px' : '0' }}
        >
          <div
            className="bg-gradient-to-br from-gray-900 to-gray-800 rounded-2xl shadow-2xl border border-white/20 max-w-md w-full p-6 pointer-events-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-center">
              <MessageSquare className="w-16 h-16 text-purple-400 mx-auto mb-4" />
              <h2 className="text-xl font-bold text-white mb-4">Требуется авторизация</h2>
              <p className="text-gray-400 mb-6">
                Войдите в систему, чтобы оставить отзыв о статье
              </p>
              <button
                onClick={onClose}
                className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-colors"
              >
                Закрыть
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!comment.trim()) {
      setError('Введите текст отзыва');
      return;
    }

    createFeedbackMutation.mutate(comment.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
  };

  return (
    <div
      className={`fixed inset-0 z-[100] ${isHeaderVisible ? 'pt-[72px] md:pt-[88px]' : ''}`}
      onClick={onClose}
      onKeyDown={handleKeyDown}
    >
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="fixed inset-0 flex items-end md:items-center justify-center pointer-events-none p-0 md:p-4"
        style={{ top: isHeaderVisible ? '72px' : '0' }}
      >
        <div
          className={`bg-gradient-to-br from-gray-900 to-gray-800 rounded-t-2xl md:rounded-2xl shadow-2xl border-t md:border border-white/20 w-full md:max-w-lg ${
            isHeaderVisible ? 'max-h-[calc(100vh-80px)] md:max-h-[calc(100vh-100px)]' : 'max-h-[90vh]'
          } overflow-hidden flex flex-col pointer-events-auto`}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-3 md:gap-4 px-4 md:px-6 pt-4 md:pt-6 pb-3 md:pb-4 border-b border-white/10">
            <div>
              <h2 className="text-lg md:text-xl font-semibold text-white">Оставить отзыв</h2>
              <p className="text-xs md:text-sm text-gray-400 mt-0.5 md:mt-1 line-clamp-1">
                {articleTitle}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors p-2 -mt-1 md:-mt-2 -mr-1 md:-mr-2"
              disabled={createFeedbackMutation.isPending}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <form
            onSubmit={handleSubmit}
            className="flex-1 overflow-y-auto px-4 md:px-6 py-3 md:py-4 space-y-3 md:space-y-4 custom-scrollbar"
          >
            {success ? (
              <div className="bg-green-500/20 border border-green-500/40 rounded-xl p-4 text-center">
                <div className="text-green-400 font-medium mb-1">Спасибо за отзыв!</div>
                <div className="text-sm text-gray-300">
                  Ваш отзыв отправлен и поможет улучшить эту статью.
                </div>
              </div>
            ) : (
              <>
                {/* Comment */}
                <div>
                  <label
                    htmlFor="wiki-feedback-comment"
                    className="block text-xs md:text-sm font-medium text-gray-300 mb-1.5 md:mb-2"
                  >
                    Ваш отзыв
                  </label>
                  <textarea
                    id="wiki-feedback-comment"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    required
                    rows={5}
                    maxLength={2000}
                    placeholder="Что вам понравилось или что можно улучшить в этой статье? Ваш отзыв поможет сделать материал лучше."
                    className="w-full px-3 md:px-4 py-2.5 md:py-3 bg-white/5 border border-white/10 rounded-xl text-sm md:text-base text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none custom-scrollbar"
                    disabled={createFeedbackMutation.isPending}
                  />
                  <div className="mt-1 text-xs text-gray-500 text-right">
                    {comment.length} / 2000
                  </div>
                </div>

                {/* Error */}
                {error && (
                  <div className="bg-red-500/20 border border-red-500/40 rounded-lg p-3 text-red-400 text-sm">
                    {error}
                  </div>
                )}
              </>
            )}
          </form>

          {/* Footer */}
          {!success && (
            <div className="flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-end gap-2 sm:gap-3 px-4 md:px-6 py-3 md:py-4 border-t border-white/10">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2.5 sm:py-2 rounded-lg border border-white/20 text-sm text-gray-300 hover:bg-white/10 active:bg-white/15 transition-all"
                disabled={createFeedbackMutation.isPending}
              >
                Отмена
              </button>
              <button
                type="submit"
                onClick={handleSubmit}
                disabled={createFeedbackMutation.isPending || !comment.trim()}
                className="px-4 py-2.5 sm:py-2 rounded-lg bg-purple-600 hover:bg-purple-700 active:bg-purple-800 text-white text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {createFeedbackMutation.isPending ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Отправка...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    <span>Отправить</span>
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
