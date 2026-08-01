import { useState } from 'react';
import type { AxiosError } from 'axios';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  CheckCircle2,
  ExternalLink,
  Loader2,
  MessageSquareText,
  SearchCheck,
  X,
  XCircle,
} from 'lucide-react';

import { wikiAPI } from '../../api/client';
import type { WikiReviewVerdict, WikiRevision } from '../../types/api';
import { translateApiError } from '../../utils/translateApiError';
import { ModalOverlay } from '../ModalOverlay';
import { toast } from '../Toast';
import { WikiContentRenderer } from './WikiContentRenderer';
import { WikiRevisionDiff, WikiRevisionMetadataDiff } from './WikiRevisionDiff';


interface WikiPeerReviewModalProps {
  revision: WikiRevision;
  onClose: () => void;
}


export function WikiPeerReviewModal({ revision, onClose }: WikiPeerReviewModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [verdict, setVerdict] = useState<WikiReviewVerdict>('support');
  const [comment, setComment] = useState('');
  const [evidenceUrl, setEvidenceUrl] = useState('');

  const mutation = useMutation({
    mutationFn: () => wikiAPI.reviewRevision(revision.id, {
      verdict,
      comment: comment.trim() || null,
      evidence_url: evidenceUrl.trim() || null,
    }),
    onSuccess: () => {
      toast.success(t('wikiPeerReview.saved'));
      queryClient.invalidateQueries({ queryKey: ['wiki-reviewable-revisions'] });
      queryClient.invalidateQueries({ queryKey: ['wiki-moderation-revisions'] });
      onClose();
    },
    onError: (error: AxiosError<{ detail?: unknown }>) => {
      toast.error(translateApiError(t, error.response?.data?.detail, t('wikiPeerReview.saveError')));
    },
  });

  const submit = () => {
    if (verdict === 'needs_changes' && !comment.trim()) {
      toast.warning(t('wikiPeerReview.commentRequired'));
      return;
    }
    mutation.mutate();
  };

  return (
    <ModalOverlay onClose={onClose} closeOnOverlayClick={false} contentClassName="min-h-full flex items-center justify-center p-3 md:p-6">
      <div className="w-full max-w-7xl max-h-[94vh] overflow-hidden rounded-3xl border border-white/15 bg-[#111827] shadow-2xl shadow-cyan-950/50">
        <header className="flex items-start justify-between gap-4 border-b border-white/10 bg-gradient-to-r from-cyan-500/10 via-blue-500/5 to-transparent px-5 py-4 md:px-7">
          <div className="min-w-0">
            <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-cyan-300"><SearchCheck className="h-4 w-4" />{t('wikiPeerReview.title')}</div>
            <h3 className="truncate text-xl font-semibold text-white">{revision.title}</h3>
            <p className="mt-1 text-sm text-slate-400">{revision.edit_summary || revision.summary}</p>
          </div>
          <button type="button" onClick={onClose} disabled={mutation.isPending} className="rounded-xl p-2 text-slate-400 hover:bg-white/10 hover:text-white disabled:opacity-40" aria-label={t('wikiAuthoring.close')}><X className="h-5 w-5" /></button>
        </header>

        <div className="max-h-[calc(94vh-270px)] overflow-y-auto p-5 md:p-7">
          {revision.base_content && (
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
                before={revision.base_content}
                after={revision.content}
                title={t('wikiDiff.changes')}
                emptyLabel={t('wikiDiff.noChanges')}
              />
            </>
          )}

          <section className={`${revision.base_content ? 'mt-5' : ''} min-w-0 rounded-2xl border border-cyan-400/20 bg-cyan-500/[0.05] p-4 md:p-5`}>
            <h4 className="mb-4 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
              {revision.base_content ? t('wikiDiff.proposedPreview') : t('wikiPeerReview.newArticle')}
            </h4>
            <WikiContentRenderer content={revision.content} className="text-sm" />
          </section>

          <section className="mt-5 rounded-2xl border border-white/10 bg-white/[0.03] p-4 md:p-5">
            <div className="mb-4 flex items-start gap-3"><MessageSquareText className="mt-0.5 h-5 w-5 text-cyan-300" /><div><h4 className="font-medium text-white">{t('wikiPeerReview.yourCheck')}</h4><p className="mt-1 text-sm leading-6 text-slate-400">{t('wikiPeerReview.advisory')}</p></div></div>
            <div className="grid gap-3 sm:grid-cols-2">
              <button type="button" onClick={() => setVerdict('support')} className={`flex items-start gap-3 rounded-xl border p-4 text-left transition ${verdict === 'support' ? 'border-emerald-400/40 bg-emerald-500/10' : 'border-white/10 bg-black/10 hover:border-white/20'}`}><CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-300" /><span><strong className="block text-sm text-white">{t('wikiPeerReview.support')}</strong><span className="mt-1 block text-xs leading-5 text-slate-400">{t('wikiPeerReview.supportDescription')}</span></span></button>
              <button type="button" onClick={() => setVerdict('needs_changes')} className={`flex items-start gap-3 rounded-xl border p-4 text-left transition ${verdict === 'needs_changes' ? 'border-amber-400/40 bg-amber-500/10' : 'border-white/10 bg-black/10 hover:border-white/20'}`}><XCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" /><span><strong className="block text-sm text-white">{t('wikiPeerReview.needsChanges')}</strong><span className="mt-1 block text-xs leading-5 text-slate-400">{t('wikiPeerReview.needsChangesDescription')}</span></span></button>
            </div>
            <label className="mt-4 block"><span className="mb-1.5 block text-sm font-medium text-slate-200">{t('wikiPeerReview.comment')}</span><textarea value={comment} onChange={(event) => setComment(event.target.value)} rows={3} maxLength={4000} className="w-full resize-y rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-white outline-none placeholder:text-slate-600 focus:border-cyan-400/60 focus:ring-2 focus:ring-cyan-500/15" placeholder={t('wikiPeerReview.commentPlaceholder')} /></label>
            <label className="mt-4 block"><span className="mb-1.5 flex items-center gap-2 text-sm font-medium text-slate-200"><ExternalLink className="h-4 w-4 text-slate-400" />{t('wikiPeerReview.evidence')}</span><input type="url" value={evidenceUrl} onChange={(event) => setEvidenceUrl(event.target.value)} maxLength={2000} className="w-full rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-white outline-none placeholder:text-slate-600 focus:border-cyan-400/60 focus:ring-2 focus:ring-cyan-500/15" placeholder="https://..." /></label>
          </section>
        </div>

        <footer className="flex items-center justify-end border-t border-white/10 px-5 py-4 md:px-7">
          <button type="button" onClick={submit} disabled={mutation.isPending} className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-cyan-950/30 transition hover:brightness-110 disabled:opacity-50">{mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <SearchCheck className="h-4 w-4" />}{t('wikiPeerReview.submit')}</button>
        </footer>
      </div>
    </ModalOverlay>
  );
}
