import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  CheckCircle2,
  Clock3,
  Loader2,
  LockKeyhole,
  MessageCircle,
  Send,
  ShieldCheck,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import type { AxiosError } from 'axios';

import { feedbackAPI } from '../api/client';
import { toast } from '../components/Toast';
import type { FeedbackStatus } from '../types/api';
import { createIdempotencyKey } from '../utils/idempotencyKey';
import { translateApiError } from '../utils/translateApiError';

const statusStyles: Record<FeedbackStatus, string> = {
  open: 'border-amber-300/25 bg-amber-300/10 text-amber-200',
  in_progress: 'border-sky-300/25 bg-sky-300/10 text-sky-200',
  resolved: 'border-emerald-300/25 bg-emerald-300/10 text-emerald-200',
  closed: 'border-slate-300/20 bg-slate-300/10 text-slate-300',
};

export function FeedbackThreadPage() {
  const { feedbackId } = useParams();
  const parsedFeedbackId = Number(feedbackId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t, i18n } = useTranslation();
  const [message, setMessage] = useState('');
  const [idempotencyKey, setIdempotencyKey] = useState(createIdempotencyKey);

  const feedbackQuery = useQuery({
    queryKey: ['feedback-thread', parsedFeedbackId],
    queryFn: () => feedbackAPI.get(parsedFeedbackId),
    enabled: Number.isInteger(parsedFeedbackId) && parsedFeedbackId > 0,
  });

  const replyMutation = useMutation({
    mutationFn: () =>
      feedbackAPI.reply(parsedFeedbackId, {
        message: message.trim(),
        idempotency_key: idempotencyKey,
      }),
    onSuccess: (updatedFeedback) => {
      queryClient.setQueryData(['feedback-thread', parsedFeedbackId], updatedFeedback);
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
      queryClient.invalidateQueries({ queryKey: ['feedback-thread', parsedFeedbackId] });
    },
  });

  const formatDate = (value: string) =>
    new Intl.DateTimeFormat(i18n.resolvedLanguage || i18n.language, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));

  if (!Number.isInteger(parsedFeedbackId) || parsedFeedbackId <= 0) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 text-center text-red-200">
        {t('feedbackThread.notFound')}
      </div>
    );
  }

  if (feedbackQuery.isLoading) {
    return (
      <div className="flex min-h-[55vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-purple-300" />
      </div>
    );
  }

  if (feedbackQuery.isError || !feedbackQuery.data) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-4 px-4 py-16 text-center">
        <MessageCircle className="h-10 w-10 text-purple-300" />
        <h1 className="text-2xl font-semibold text-white">{t('feedbackThread.notFoundTitle')}</h1>
        <p className="max-w-lg text-sm text-slate-300">{t('feedbackThread.notFound')}</p>
        <button
          type="button"
          onClick={() => navigate('/')}
          className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-white/10"
        >
          {t('feedbackThread.toCatalog')}
        </button>
      </div>
    );
  }

  const feedback = feedbackQuery.data;
  const conversationLocked = feedback.status === 'resolved' || feedback.status === 'closed';

  return (
    <div className="mx-auto w-full max-w-4xl px-3 py-6 sm:px-6 sm:py-10">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="mb-4 inline-flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-slate-300 transition-colors hover:bg-white/5 hover:text-white"
      >
        <ArrowLeft className="h-4 w-4" />
        {t('feedbackThread.back')}
      </button>

      <section className="overflow-hidden rounded-2xl border border-white/10 bg-slate-950/55 shadow-2xl shadow-purple-950/20 backdrop-blur-xl">
        <header className="border-b border-white/10 bg-gradient-to-r from-purple-500/10 via-transparent to-cyan-400/5 px-5 py-5 sm:px-7 sm:py-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                <span>{t(`feedback.types.${feedback.type}.label`)}</span>
                <span aria-hidden="true">·</span>
                <span>#{feedback.id}</span>
              </div>
              <h1 className="break-words text-xl font-semibold text-white sm:text-2xl">
                {feedback.subject}
              </h1>
            </div>
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
          </div>
        </header>

        <div className="space-y-5 px-4 py-6 sm:px-7">
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
                    <span className="text-slate-500">{formatDate(threadMessage.created_at)}</span>
                  </div>
                  <div
                    className={`whitespace-pre-wrap break-words rounded-2xl px-4 py-3 text-left text-sm leading-6 shadow-lg ${
                      fromSupport
                        ? 'rounded-tl-md border border-cyan-300/15 bg-cyan-950/35 text-slate-100'
                        : 'rounded-tr-md border border-purple-300/20 bg-purple-500/15 text-white'
                    }`}
                  >
                    {threadMessage.message}
                  </div>
                </div>
              </article>
            );
          })}
        </div>

        <footer className="border-t border-white/10 bg-black/15 px-4 py-5 sm:px-7">
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
              <label htmlFor="feedback-thread-reply" className="text-sm font-medium text-white">
                {t('feedbackThread.replyLabel')}
              </label>
              <textarea
                id="feedback-thread-reply"
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                rows={4}
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
    </div>
  );
}
