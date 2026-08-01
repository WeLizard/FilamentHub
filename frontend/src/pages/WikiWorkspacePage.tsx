import { useEffect, useState } from 'react';
import type { AxiosError } from 'axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  BookOpenCheck,
  CheckCircle2,
  Clock3,
  ExternalLink,
  FilePenLine,
  Inbox,
  Loader2,
  MessageSquareText,
  Plus,
  RotateCcw,
  Undo2,
  XCircle,
} from 'lucide-react';

import { wikiAPI } from '../api/client';
import { ConfirmModal } from '../components/ConfirmModal';
import { SEOHead } from '../components/SEOHead';
import { toast } from '../components/Toast';
import { WikiAuthoringModal } from '../components/wiki';
import type { WikiLanguage, WikiRevision, WikiRevisionStatus } from '../types/api';
import { translateApiError } from '../utils/translateApiError';

type WorkspaceFilter = 'all' | WikiRevisionStatus;

const FILTERS: WorkspaceFilter[] = [
  'all',
  'draft',
  'pending_review',
  'rejected',
  'published',
  'withdrawn',
];

const STATUS_TONE: Record<WikiRevisionStatus, string> = {
  draft: 'border-blue-400/20 bg-blue-500/10 text-blue-200',
  pending_review: 'border-amber-400/20 bg-amber-500/10 text-amber-200',
  published: 'border-emerald-400/20 bg-emerald-500/10 text-emerald-200',
  rejected: 'border-rose-400/20 bg-rose-500/10 text-rose-200',
  withdrawn: 'border-slate-400/20 bg-slate-500/10 text-slate-300',
};

function RevisionStatusIcon({ status }: { status: WikiRevisionStatus }) {
  if (status === 'published') return <CheckCircle2 className="h-4 w-4" />;
  if (status === 'rejected') return <XCircle className="h-4 w-4" />;
  if (status === 'pending_review') return <Clock3 className="h-4 w-4" />;
  if (status === 'withdrawn') return <Undo2 className="h-4 w-4" />;
  return <FilePenLine className="h-4 w-4" />;
}

export function WikiWorkspacePage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const languageCode = i18n.resolvedLanguage?.split('-')[0];
  const language: WikiLanguage = languageCode === 'ru' || languageCode === 'zh' ? languageCode : 'en';
  const [filter, setFilter] = useState<WorkspaceFilter>('all');
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<WikiRevision | 'new' | null>(null);
  const [withdrawTarget, setWithdrawTarget] = useState<WikiRevision | null>(null);

  useEffect(() => setPage(1), [filter]);

  const revisionsQuery = useQuery({
    queryKey: ['wiki-own-revisions', filter, page],
    queryFn: () => wikiAPI.listOwnRevisions({
      status: filter === 'all' ? undefined : filter,
      page,
      page_size: 12,
    }),
  });

  const categoriesQuery = useQuery({
    queryKey: ['wiki-author-categories', language],
    queryFn: async () => {
      const localized = await wikiAPI.listCategories({ page: 1, page_size: 100, space: 'knowledge', language });
      if (localized.items.length || language === 'ru') return localized;
      return wikiAPI.listCategories({ page: 1, page_size: 100, space: 'knowledge', language: 'ru' });
    },
    staleTime: 60_000,
  });

  const retryMutation = useMutation({
    mutationFn: (revisionId: number) => wikiAPI.retryRevision(revisionId),
    onSuccess: (revision) => {
      void queryClient.invalidateQueries({ queryKey: ['wiki-own-revisions'] });
      setEditing(revision);
    },
    onError: (error: AxiosError<{ detail?: unknown }>) => {
      toast.error(translateApiError(t, error.response?.data?.detail, t('wikiWorkspace.retryError')));
    },
  });

  const withdrawMutation = useMutation({
    mutationFn: (revisionId: number) => wikiAPI.withdrawRevision(revisionId),
    onSuccess: () => {
      toast.success(t('wikiWorkspace.withdrawn'));
      setWithdrawTarget(null);
      void queryClient.invalidateQueries({ queryKey: ['wiki-own-revisions'] });
    },
    onError: (error: AxiosError<{ detail?: unknown }>) => {
      toast.error(translateApiError(t, error.response?.data?.detail, t('wikiWorkspace.withdrawError')));
    },
  });

  const data = revisionsQuery.data;
  const categories = categoriesQuery.data?.items ?? [];

  return (
    <>
      <SEOHead
        title={t('wikiWorkspace.seoTitle')}
        description={t('wikiWorkspace.seoDescription')}
        url="/wiki/workspace"
        allowAI={false}
      />

      <main className="mx-auto max-w-6xl px-4 py-6 md:px-6 md:py-10">
        <button type="button" onClick={() => navigate('/wiki')} className="mb-5 inline-flex items-center gap-2 text-sm text-slate-400 transition hover:text-white">
          <ArrowLeft className="h-4 w-4" />{t('wikiWorkspace.backToWiki')}
        </button>

        <section className="relative mb-6 overflow-hidden rounded-3xl border border-cyan-300/15 bg-[#101a31] p-6 shadow-2xl shadow-cyan-950/20 md:p-8">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(34,211,238,0.16),transparent_38%),radial-gradient(circle_at_bottom_left,rgba(139,92,246,0.15),transparent_40%)]" />
          <div className="relative flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
            <div className="flex items-start gap-4">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-cyan-400/10 text-cyan-200 ring-1 ring-cyan-300/20">
                <BookOpenCheck className="h-6 w-6" />
              </span>
              <div>
                <h1 className="text-2xl font-bold text-white md:text-3xl">{t('wikiWorkspace.title')}</h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400 md:text-base">{t('wikiWorkspace.description')}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setEditing('new')}
              disabled={categoriesQuery.isLoading || categories.length === 0}
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-500 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-cyan-950/40 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Plus className="h-4 w-4" />{t('wikiWorkspace.newArticle')}
            </button>
          </div>
        </section>

        <div className="mb-5 flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label={t('wikiWorkspace.filters')}>
          {FILTERS.map((status) => (
            <button
              key={status}
              type="button"
              role="tab"
              aria-selected={filter === status}
              onClick={() => setFilter(status)}
              className={`shrink-0 rounded-full border px-3.5 py-2 text-sm transition ${filter === status ? 'border-cyan-300/35 bg-cyan-400/15 text-cyan-100' : 'border-white/10 bg-white/[0.035] text-slate-400 hover:border-white/20 hover:text-white'}`}
            >
              {status === 'all' ? t('wikiWorkspace.all') : t(`wikiAuthoring.status.${status}`)}
            </button>
          ))}
        </div>

        {revisionsQuery.isLoading ? (
          <div className="flex min-h-72 items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-cyan-300" /></div>
        ) : revisionsQuery.isError ? (
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-8 text-center text-red-200">
            <p>{t('wikiWorkspace.loadError')}</p>
            <button type="button" onClick={() => revisionsQuery.refetch()} className="mt-4 rounded-lg border border-red-300/20 px-4 py-2 text-sm hover:bg-red-400/10">{t('wikiWorkspace.retry')}</button>
          </div>
        ) : !data?.items.length ? (
          <div className="rounded-3xl border border-dashed border-white/15 bg-white/[0.025] px-6 py-16 text-center">
            <Inbox className="mx-auto h-11 w-11 text-slate-600" />
            <h2 className="mt-4 text-lg font-semibold text-white">{t('wikiWorkspace.emptyTitle')}</h2>
            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">{t('wikiWorkspace.emptyDescription')}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {data.items.map((revision) => (
              <article key={revision.id} className="rounded-2xl border border-white/10 bg-[#111827]/80 p-4 transition hover:border-white/15 md:p-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div className="min-w-0">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${STATUS_TONE[revision.status]}`}>
                        <RevisionStatusIcon status={revision.status} />
                        {t(`wikiAuthoring.status.${revision.status}`)}
                      </span>
                      <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-xs text-slate-400">v{revision.revision_number}</span>
                      <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-xs uppercase text-slate-500">{revision.article_language}</span>
                    </div>
                    <h2 className="truncate text-lg font-semibold text-white">{revision.title}</h2>
                    <p className="mt-1 line-clamp-2 text-sm leading-6 text-slate-400">{revision.edit_summary || revision.summary}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
                      <span>{t('wikiWorkspace.updated', { date: new Date(revision.updated_at).toLocaleString(i18n.resolvedLanguage) })}</span>
                      {revision.peer_reviews.length > 0 && <span className="inline-flex items-center gap-1"><MessageSquareText className="h-3.5 w-3.5" />{t('wikiWorkspace.reviews', { count: revision.peer_reviews.length })}</span>}
                    </div>
                    {revision.status === 'rejected' && revision.review_note && (
                      <div className="mt-3 rounded-xl border border-amber-400/15 bg-amber-500/[0.06] px-3 py-2 text-sm text-amber-100/80">
                        <span className="font-medium text-amber-200">{t('wikiWorkspace.editorNote')}</span> {revision.review_note}
                      </div>
                    )}
                  </div>

                  <div className="flex shrink-0 flex-wrap gap-2 lg:justify-end">
                    {revision.status === 'draft' && (
                      <button type="button" onClick={() => setEditing(revision)} className="inline-flex items-center gap-2 rounded-xl bg-blue-500/15 px-3.5 py-2 text-sm font-medium text-blue-200 transition hover:bg-blue-500/25">
                        <FilePenLine className="h-4 w-4" />{t('wikiWorkspace.continueEditing')}
                      </button>
                    )}
                    {revision.status === 'pending_review' && (
                      <button type="button" onClick={() => setWithdrawTarget(revision)} className="inline-flex items-center gap-2 rounded-xl border border-amber-400/15 bg-amber-500/[0.06] px-3.5 py-2 text-sm font-medium text-amber-200 transition hover:bg-amber-500/15">
                        <Undo2 className="h-4 w-4" />{t('wikiWorkspace.withdraw')}
                      </button>
                    )}
                    {revision.status === 'rejected' && (
                      <button type="button" onClick={() => retryMutation.mutate(revision.id)} disabled={retryMutation.isPending} className="inline-flex items-center gap-2 rounded-xl bg-rose-500/15 px-3.5 py-2 text-sm font-medium text-rose-100 transition hover:bg-rose-500/25 disabled:opacity-40">
                        {retryMutation.isPending && retryMutation.variables === revision.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                        {t('wikiWorkspace.createCorrection')}
                      </button>
                    )}
                    {revision.status === 'published' && (
                      <button type="button" onClick={() => navigate(`/wiki/articles/${revision.article_slug}`)} className="inline-flex items-center gap-2 rounded-xl bg-emerald-500/15 px-3.5 py-2 text-sm font-medium text-emerald-100 transition hover:bg-emerald-500/25">
                        <ExternalLink className="h-4 w-4" />{t('wikiWorkspace.openArticle')}
                      </button>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}

        {(data?.total_pages ?? 0) > 1 && (
          <nav className="mt-6 flex items-center justify-center gap-3" aria-label={t('wikiWorkspace.pagination')}>
            <button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)} className="rounded-xl border border-white/10 px-4 py-2 text-sm text-slate-300 transition hover:bg-white/5 disabled:opacity-30">{t('wikiWorkspace.previous')}</button>
            <span className="text-sm text-slate-500">{t('wikiWorkspace.page', { page, total: data?.total_pages })}</span>
            <button type="button" disabled={page >= (data?.total_pages ?? 1)} onClick={() => setPage((value) => value + 1)} className="rounded-xl border border-white/10 px-4 py-2 text-sm text-slate-300 transition hover:bg-white/5 disabled:opacity-30">{t('wikiWorkspace.next')}</button>
          </nav>
        )}
      </main>

      {editing && (
        <WikiAuthoringModal
          categories={categories}
          revision={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            void queryClient.invalidateQueries({ queryKey: ['wiki-own-revisions'] });
          }}
        />
      )}

      <ConfirmModal
        isOpen={Boolean(withdrawTarget)}
        onClose={() => setWithdrawTarget(null)}
        onConfirm={() => withdrawTarget && withdrawMutation.mutate(withdrawTarget.id)}
        title={t('wikiWorkspace.withdrawTitle')}
        message={t('wikiWorkspace.withdrawMessage')}
        confirmText={t('wikiWorkspace.withdrawConfirm')}
        cancelText={t('wikiWorkspace.cancel')}
        isLoading={withdrawMutation.isPending}
        variant="warning"
      />
    </>
  );
}
