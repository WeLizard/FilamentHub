/** Модальное окно для отзыва на wiki статью */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Send, MessageSquare } from 'lucide-react';
import { useMutation } from '@tanstack/react-query';
import { feedbackAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { useAuth } from '../contexts/AuthContext';
import { ModalOverlay } from './ModalOverlay';
import type { AxiosError } from 'axios';

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
  const { t } = useTranslation();
  const { user } = useAuth();
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Мутация для создания отзыва через общий Feedback API
  const createFeedbackMutation = useMutation({
    mutationFn: (commentText: string) =>
      feedbackAPI.create({
        type: 'other',
        subject: `Wiki feedback: ${articleTitle}`,
        message: commentText,
        source: 'wiki_article',
        source_url: window.location.href,
        source_id: undefined, // TODO: можно передавать article_id если нужно
      }),
    onSuccess: () => {
      setSuccess(true);
      // Закрываем модалку через 2 секунды
      setTimeout(() => {
        setComment('');
        setSuccess(false);
        onClose();
      }, 2000);
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      console.error('Error creating feedback:', err);
      setError(translateApiError(t, err?.response?.data?.detail, t('wikiFeedback.sendError')));
    },
  });

  // Показываем модалку только для авторизованных пользователей
  if (!isOpen) return null;

  // Если пользователь не авторизован, показываем сообщение
  if (!user) {
    return (
      <ModalOverlay onClose={onClose} className="!bg-black/60">
        <div
          className="bg-gradient-to-br from-gray-900 to-gray-800 rounded-2xl shadow-2xl border border-white/20 max-w-md w-full p-6"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="text-center">
            <MessageSquare className="w-16 h-16 text-purple-400 mx-auto mb-4" />
            <h2 className="text-xl font-bold text-white mb-4">{t('wikiFeedback.authRequired')}</h2>
            <p className="text-gray-400 mb-6">
              {t('wikiFeedback.authMessage')}
            </p>
            <button
              onClick={onClose}
              className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-colors"
            >
              {t('wikiFeedback.close')}
            </button>
          </div>
        </div>
      </ModalOverlay>
    );
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!comment.trim()) {
      setError(t('wikiFeedback.emptyError'));
      return;
    }

    createFeedbackMutation.mutate(comment.trim());
  };

  return (
    <ModalOverlay onClose={onClose} className="!bg-black/60">
      <div
        className="bg-gradient-to-br from-gray-900 to-gray-800 rounded-t-2xl md:rounded-2xl shadow-2xl border-t md:border border-white/20 w-full md:max-w-lg max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
          {/* Header */}
          <div className="flex items-start justify-between gap-3 md:gap-4 px-4 md:px-6 pt-4 md:pt-6 pb-3 md:pb-4 border-b border-white/10">
            <div>
              <h2 className="text-lg md:text-xl font-semibold text-white">{t('wikiFeedback.title')}</h2>
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
                <div className="text-green-400 font-medium mb-1">{t('wikiFeedback.thankYou')}</div>
                <div className="text-sm text-gray-300">
                  {t('wikiFeedback.feedbackSent')}
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
                    {t('wikiFeedback.yourFeedback')}
                  </label>
                  <textarea
                    id="wiki-feedback-comment"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    required
                    rows={5}
                    maxLength={2000}
                    placeholder={t('wikiFeedback.placeholder')}
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
                {t('wikiFeedback.cancel')}
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
                    <span>{t('wikiFeedback.sending')}</span>
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    <span>{t('wikiFeedback.send')}</span>
                  </>
                )}
              </button>
            </div>
          )}
        </div>
    </ModalOverlay>
  );
};
