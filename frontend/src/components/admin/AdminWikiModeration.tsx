import { useState } from 'react';
import type { AxiosError } from 'axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  CheckCircle2,
  Clock3,
  FilePenLine,
  Loader2,
  MessageSquareText,
  ShieldCheck,
  UserRound,
  X,
  XCircle,
} from 'lucide-react';

import { wikiAPI } from '../../api/client';
import type { WikiRevision } from '../../types/api';
import { translateApiError } from '../../utils/translateApiError';
import { ModalOverlay } from '../ModalOverlay';
import { toast } from '../Toast';
import { WikiContentRenderer } from '../wiki/WikiContentRenderer';
import { WikiRevisionDiff, WikiRevisionMetadataDiff } from '../wiki/WikiRevisionDiff';

function ModerationModal({ revision, onClose }: { revision: WikiRevision; onClose: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [reviewNote, setReviewNote] = useState('');

  const currentContent = revision.base_content;

  const decisionMutation = useMutation({
    mutationFn: (decision: 'publish' | 'reject') => wikiAPI.decideRevision(revision.id, {
      decision,
      review_note: reviewNote.trim() || null,
    }),
    onSuccess: (_, decision) => {
      toast.success(decision === 'publish' ? t('adminWiki.moderation.published') : t('adminWiki.moderation.rejected'));
      queryClient.invalidateQueries({ queryKey: ['wiki-moderation-revisions'] });
      queryClient.invalidateQueries({ queryKey: ['admin-wiki-articles'] });
      queryClient.invalidateQueries({ queryKey: ['wiki-categories'] });
      onClose();
    },
    onError: (error: AxiosError<{ detail?: unknown }>) => {
      toast.error(translateApiError(t, error.response?.data?.detail, t('adminWiki.moderation.decisionError')));
    },
  });

  const reject = () => {
    if (!reviewNote.trim()) {
      toast.warning(t('adminWiki.moderation.rejectionNoteRequired'));
      return;
    }
    decisionMutation.mutate('reject');
  };

  return (
    <ModalOverlay onClose={onClose} closeOnOverlayClick={false} contentClassName="min-h-full flex items-center justify-center p-3 md:p-6">
      <div className="w-full max-w-7xl max-h-[94vh] overflow-hidden rounded-3xl border border-white/15 bg-[#111827] shadow-2xl shadow-purple-950/60">
        <header className="flex items-start justify-between gap-4 border-b border-white/10 bg-gradient-to-r from-purple-500/10 via-blue-500/5 to-transparent px-5 py-4 md:px-7">
          <div className="min-w-0">
            <div className="mb-1 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-purple-300"><ShieldCheck className="h-4 w-4" />{t('adminWiki.moderation.reviewTitle')}</div>
            <h3 className="truncate text-xl font-semibold text-white">{revision.title}</h3>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
              <span className="flex items-center gap-1.5"><UserRound className="h-3.5 w-3.5" />{revision.created_by_username || t('adminWiki.moderation.unknownAuthor')}</span>
              <span>v{revision.revision_number}</span>
              <span>{revision.article_language.toUpperCase()}</span>
              <span>{t(`wikiAuthoring.authorship.${revision.authorship}`)}</span>
            </div>
          </div>
          <button type="button" onClick={onClose} disabled={decisionMutation.isPending} className="rounded-xl p-2 text-slate-400 hover:bg-white/10 hover:text-white disabled:opacity-40"><X className="h-5 w-5" /></button>
        </header>

        <div className="max-h-[calc(94vh-210px)] overflow-y-auto p-5 md:p-7">
          {revision.edit_summary && (
            <div className="mb-5 flex items-start gap-3 rounded-2xl border border-blue-400/15 bg-blue-500/[0.06] p-4">
              <MessageSquareText className="mt-0.5 h-4 w-4 shrink-0 text-blue-300" />
              <div><div className="text-xs font-medium uppercase tracking-wider text-blue-300/80">{t('adminWiki.moderation.changeReason')}</div><p className="mt-1 text-sm leading-6 text-slate-300">{revision.edit_summary}</p></div>
            </div>
          )}

          {currentContent && (
            <>
              <WikiRevisionMetadataDiff
                title={t('wikiDiff.metadata')}
                items={[
                  { label: t('wikiAuthoring.title'), before: revision.base_title || '', after: revision.title },
                  { label: t('wikiAuthoring.summary'), before: revision.base_summary || '', after: revision.summary },
                  { label: t('wikiAuthoring.tags'), before: (revision.base_tags || []).join(', '), after: (revision.tags || []).join(', ') },
                ]}
              />
              <WikiRevisionDiff
                before={currentContent}
                after={revision.content}
                title={t('wikiDiff.changes')}
                emptyLabel={t('wikiDiff.noChanges')}
              />
            </>
          )}

          <section className={`${currentContent ? 'mt-5' : ''} min-w-0 rounded-2xl border border-purple-400/20 bg-purple-500/[0.06] p-4 md:p-5`}>
            <h4 className="mb-4 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
              {currentContent ? t('wikiDiff.proposedPreview') : t('adminWiki.moderation.newArticle')}
            </h4>
            <WikiContentRenderer content={revision.content} className="text-sm" privateMedia />
          </section>

          {revision.peer_reviews.length > 0 && (
            <section className="mt-5 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <h4 className="mb-3 text-sm font-medium text-white">{t('adminWiki.moderation.communityChecks', { count: revision.peer_reviews.length })}</h4>
              <div className="space-y-2">
                {revision.peer_reviews.map((review) => (
                  <div key={review.id} className="flex items-start gap-3 rounded-xl bg-black/10 px-3 py-2.5 text-sm">
                    {review.verdict === 'support' ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />}
                    <div><span className="font-medium text-slate-200">{review.reviewer_username || t('adminWiki.moderation.unknownAuthor')}</span>{review.comment && <p className="mt-1 text-slate-400">{review.comment}</p>}</div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <label className="mt-5 block">
            <span className="mb-1.5 block text-sm font-medium text-slate-200">{t('adminWiki.moderation.editorNote')}</span>
            <textarea value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} rows={3} maxLength={4000} className="w-full resize-y rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-white outline-none placeholder:text-slate-600 focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/15" placeholder={t('adminWiki.moderation.editorNotePlaceholder')} />
          </label>
        </div>

        <footer className="flex flex-col-reverse gap-3 border-t border-white/10 px-5 py-4 sm:flex-row sm:items-center sm:justify-end md:px-7">
          <button type="button" onClick={reject} disabled={decisionMutation.isPending} className="inline-flex items-center justify-center gap-2 rounded-xl border border-red-400/25 bg-red-500/10 px-4 py-2.5 text-sm font-medium text-red-200 hover:bg-red-500/20 disabled:opacity-50">{decisionMutation.isPending && decisionMutation.variables === 'reject' ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}{t('adminWiki.moderation.reject')}</button>
          <button type="button" onClick={() => decisionMutation.mutate('publish')} disabled={decisionMutation.isPending} className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-emerald-950/30 hover:brightness-110 disabled:opacity-50">{decisionMutation.isPending && decisionMutation.variables === 'publish' ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}{t('adminWiki.moderation.publish')}</button>
        </footer>
      </div>
    </ModalOverlay>
  );
}

export function AdminWikiModeration() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<WikiRevision | null>(null);
  const { data, isLoading, isError } = useQuery({
    queryKey: ['wiki-moderation-revisions', page],
    queryFn: () => wikiAPI.listModerationRevisions({ status: 'pending_review', page, page_size: 20 }),
  });

  if (isLoading) return <div className="flex justify-center py-16"><Loader2 className="h-8 w-8 animate-spin text-purple-300" /></div>;
  if (isError) return <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-6 text-center text-red-200">{t('adminWiki.moderation.loadError')}</div>;

  return (
    <div>
      <div className="mb-5 rounded-2xl border border-purple-400/15 bg-gradient-to-r from-purple-500/10 to-blue-500/5 p-5">
        <div className="flex items-start gap-3"><ShieldCheck className="mt-0.5 h-5 w-5 text-purple-300" /><div><h3 className="font-semibold text-white">{t('adminWiki.moderation.queueTitle')}</h3><p className="mt-1 text-sm leading-6 text-slate-400">{t('adminWiki.moderation.queueDescription')}</p></div></div>
      </div>

      {!data?.items.length ? (
        <div className="rounded-2xl border border-dashed border-white/10 py-16 text-center"><CheckCircle2 className="mx-auto mb-3 h-10 w-10 text-emerald-300/70" /><h3 className="font-medium text-white">{t('adminWiki.moderation.emptyTitle')}</h3><p className="mt-1 text-sm text-slate-500">{t('adminWiki.moderation.emptyDescription')}</p></div>
      ) : (
        <div className="space-y-3">
          {data.items.map((revision) => (
            <button key={revision.id} type="button" onClick={() => setSelected(revision)} className="group w-full rounded-2xl border border-white/10 bg-white/[0.04] p-4 text-left transition hover:border-purple-400/25 hover:bg-white/[0.07] md:p-5">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0"><div className="mb-1 flex flex-wrap items-center gap-2"><span className="truncate font-semibold text-white group-hover:text-purple-200">{revision.title}</span><span className="rounded-full bg-purple-500/10 px-2 py-0.5 text-[11px] text-purple-300">v{revision.revision_number}</span></div><p className="line-clamp-2 text-sm text-slate-400">{revision.edit_summary || revision.summary}</p></div>
                <div className="flex shrink-0 flex-wrap items-center gap-3 text-xs text-slate-500"><span className="flex items-center gap-1.5"><UserRound className="h-3.5 w-3.5" />{revision.created_by_username || t('adminWiki.moderation.unknownAuthor')}</span><span className="flex items-center gap-1.5"><Clock3 className="h-3.5 w-3.5" />{revision.submitted_at ? new Date(revision.submitted_at).toLocaleDateString() : '—'}</span>{revision.peer_reviews.length > 0 && <span className="flex items-center gap-1.5"><MessageSquareText className="h-3.5 w-3.5" />{revision.peer_reviews.length}</span>}<FilePenLine className="h-4 w-4 text-purple-300" /></div>
              </div>
            </button>
          ))}
        </div>
      )}

      {(data?.total_pages ?? 0) > 1 && <div className="mt-5 flex justify-center gap-2"><button type="button" disabled={page === 1} onClick={() => setPage((value) => value - 1)} className="rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300 disabled:opacity-30">{t('adminWiki.moderation.previous')}</button><span className="px-3 py-2 text-sm text-slate-500">{page} / {data?.total_pages}</span><button type="button" disabled={page === data?.total_pages} onClick={() => setPage((value) => value + 1)} className="rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300 disabled:opacity-30">{t('adminWiki.moderation.next')}</button></div>}
      {selected && <ModerationModal revision={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
