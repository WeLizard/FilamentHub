import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CheckCircle2,
  Clock3,
  Loader2,
  LockKeyhole,
  MessageCircle,
  Send,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { AxiosError } from 'axios';

import { feedbackAPI } from '../api/client';
import { FeedbackImages } from './FeedbackImages';
import { toast } from './Toast';
import type { FeedbackStatus } from '../types/api';
import { createIdempotencyKey } from '../utils/idempotencyKey';
import { translateApiError } from '../utils/translateApiError';
import { formatMediumDateTime } from '../utils/formatDate';

const statusStyles: Record<FeedbackStatus, string> = {
  open: 'border-amber-300/25 bg-amber-300/10 text-amber-200',
  in_progress: 'border-sky-300/25 bg-sky-300/10 text-sky-200',
  resolved: 'border-emerald-300/25 bg-emerald-300/10 text-emerald-200',
  closed: 'border-slate-300/20 bg-slate-300/10 text-slate-300',
};

interface FeedbackThreadViewProps {
  feedbackId: number;
  /** Present when the thread is shown in a dialog over the current page. */
  onClose?: () => void;
  titleId?: string;
}

/** A user's conversation with support, shared by the thread page and the bell dialog. */
export function FeedbackThreadView({ feedbackId, onClose, titleId }: FeedbackThreadViewProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const [message, setMessage] = useState('');
  const [idempotencyKey, setIdempotencyKey] = useState(createIdempotencyKey);
  const messagesRef = useRef<HTMLDivElement>(null);
  const inDialog = Boolean(onClose);

  const feedbackQuery = useQuery({
    queryKey: ['feedback-thread', feedbackId],
    queryFn: () => feedbackAPI.get(feedbackId),
    // A missing or inaccessible thread is a stable, user-facing state. Retrying
    // it only leaves the route looking blank behind a spinner before the same
    // not-found view can be shown.
    retry: false,
  });

  const replyMutation = useMutation({
    mutationFn: () =>
      feedbackAPI.reply(feedbackId, {
        message: message.trim(),
        idempotency_key: idempotencyKey,
      }),
    onSuccess: (updatedFeedback) => {
      queryClient.setQueryData(['feedback-thread', feedbackId], updatedFeedback);
      queryClient.invalidateQueries({ queryKey: ['my-feedback'] });
      setMessage('');
      setIdempotencyKey(createIdempotencyKey());
      toast.success(t('feedbackThread.replySent'));
    },
    onError: (error: AxiosError<{ detail?: unknown }>) => {
      toast.error(
        translateApiError(
          t,
          error.response?.data?.detail,
          t('feedbackThread.replyError'),
        ),
      );
      queryClient.invalidateQueries({ queryKey: ['feedback-thread', feedbackId] });
    },
  });

  const latestMessageId = feedbackQuery.data?.messages.at(-1)?.id;
  useEffect(() => {
    const container = messagesRef.current;
    if (inDialog && container) container.scrollTop = container.scrollHeight;
  }, [inDialog, latestMessageId]);

  const closeButton = onClose ? (
    <button
      type="button"
      onClick={onClose}
      aria-label={t('common.close')}
      className="-mr-2 -mt-1 flex h-10 w-10 flex-none items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
    >
      <X className="h-5 w-5" />
    </button>
  ) : null;

  if (feedbackQuery.isLoading) {
    return (
      <div className={`flex items-center justify-center ${inDialog ? 'min-h-48' : 'min-h-[55vh]'}`}>
        <Loader2 className="h-8 w-8 animate-spin text-purple-300" />
      </div>
    );
  }

  if (feedbackQuery.isError || !feedbackQuery.data) {
    return (
      <div className="relative mx-auto flex max-w-3xl flex-col items-center gap-4 px-4 py-16 text-center">
        {closeButton && <div className="absolute right-4 top-3">{closeButton}</div>}
        <MessageCircle className="h-10 w-10 text-purple-300" />
        <h1 id={titleId} className="text-2xl font-semibold text-white">{t('feedbackThread.notFoundTitle')}</h1>
        <p className="max-w-lg text-sm text-slate-300">{t('feedbackThread.notFound')}</p>
        {!inDialog && (
          <button
            type="button"
            onClick={() => navigate('/')}
            className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-white/10"
          >
            {t('feedbackThread.toCatalog')}
          </button>
        )}
      </div>
    );
  }

  const feedback = feedbackQuery.data;
  const conversationLocked = feedback.status === 'resolved' || feedback.status === 'closed';
  const padX = inDialog ? 'px-4 sm:px-6' : 'px-4 sm:px-7';

  return (
    <section
      className={`flex flex-col overflow-hidden rounded-2xl border border-white/10 bg-slate-950/55 shadow-2xl shadow-purple-950/20 backdrop-blur-xl ${
        inDialog ? 'max-h-[85vh] bg-slate-950/95' : ''
      }`}
    >
      <header className={`border-b border-white/10 bg-gradient-to-r from-purple-500/10 via-transparent to-cyan-400/5 ${padX} ${inDialog ? 'py-4' : 'py-5 sm:py-6'}`}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span>{t(`feedback.types.${feedback.type}.label`)}</span>
              <span aria-hidden="true">·</span>
              <span>#{feedback.id}</span>
            </div>
            <h1 id={titleId} className={`break-words font-semibold text-white ${inDialog ? 'text-lg' : 'text-xl sm:text-2xl'}`}>
              {feedback.subject}
            </h1>
          </div>
          <div className="flex items-start gap-2">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold ${statusStyles[feedback.status]}`}
            >
              {conversationLocked ? (
                <CheckCircle2 className="h-3.5 w-3.5" />
              ) : (
                <Clock3 className="h-3.5 w-3.5" />
              )}
              {t(`feedbackThread.status.${feedback.status}`)}
            </span>
            {closeButton}
          </div>
        </div>
      </header>

      <div
        ref={messagesRef}
        className={`space-y-5 ${padX} ${inDialog ? 'min-h-0 flex-1 overflow-y-auto py-4 custom-scrollbar' : 'py-6'}`}
      >
        {feedback.messages.map((threadMessage) => {
          const fromSupport = threadMessage.author_type === 'admin';
          return (
            <article
              key={threadMessage.id}
              className={`flex ${fromSupport ? 'justify-start' : 'justify-end'}`}
            >
              <div className={`max-w-[92%] sm:max-w-[78%] ${fromSupport ? '' : 'text-right'}`}>
                <div
                  className={`mb-1.5 flex items-center gap-2 text-xs ${
                    fromSupport ? 'justify-start text-cyan-200' : 'justify-end text-purple-200'
                  }`}
                >
                  {fromSupport && <ShieldCheck className="h-3.5 w-3.5" />}
                  <span>
                    {fromSupport
                      ? t('feedbackThread.support')
                      : t('feedbackThread.you')}
                  </span>
                  <span className="text-slate-500">{formatMediumDateTime(threadMessage.created_at)}</span>
                </div>
                {threadMessage.message && (
                  <div
                    className={`whitespace-pre-wrap break-words rounded-2xl px-4 py-3 text-left text-sm leading-6 shadow-lg ${
                      fromSupport
                        ? 'rounded-tl-md border border-cyan-300/15 bg-cyan-950/35 text-slate-100'
                        : 'rounded-tr-md border border-purple-300/20 bg-purple-500/15 text-white'
                    }`}
                  >
                    {threadMessage.message}
                  </div>
                )}
                <FeedbackImages attachments={threadMessage.attachments} />
              </div>
            </article>
          );
        })}
      </div>

      <footer className={`border-t border-white/10 bg-black/15 ${padX} ${inDialog ? 'py-4' : 'py-5'}`}>
        {conversationLocked ? (
          <div className="flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.035] p-4">
            <LockKeyhole className="mt-0.5 h-5 w-5 flex-none text-slate-300" />
            <div>
              <h2 className="text-sm font-semibold text-white">
                {t('feedbackThread.lockedTitle')}
              </h2>
              <p className="mt-1 text-sm leading-5 text-slate-400">
                {t('feedbackThread.lockedDescription')}
              </p>
            </div>
          </div>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (message.trim()) {
                replyMutation.mutate();
              }
            }}
            className="space-y-3"
          >
            <label htmlFor={`feedback-thread-reply-${feedbackId}`} className="text-sm font-medium text-white">
              {t('feedbackThread.replyLabel')}
            </label>
            <textarea
              id={`feedback-thread-reply-${feedbackId}`}
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && message.trim()) {
                  event.preventDefault();
                  replyMutation.mutate();
                }
              }}
              rows={inDialog ? 3 : 4}
              maxLength={10_000}
              placeholder={t('feedbackThread.replyPlaceholder')}
              disabled={replyMutation.isPending}
              className="w-full resize-y rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-purple-300/40 focus:outline-none focus:ring-2 focus:ring-purple-400/25 disabled:opacity-60"
            />
            <div className="flex items-center justify-between gap-4">
              <span className="text-xs text-slate-500">
                {t('feedbackThread.characters', { count: message.length })}
              </span>
              <button
                type="submit"
                disabled={!message.trim() || replyMutation.isPending}
                className="inline-flex items-center gap-2 rounded-xl bg-purple-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-purple-950/30 transition-colors hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {replyMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                {replyMutation.isPending
                  ? t('feedbackThread.sending')
                  : t('feedbackThread.send')}
              </button>
            </div>
          </form>
        )}
      </footer>
    </section>
  );
}
