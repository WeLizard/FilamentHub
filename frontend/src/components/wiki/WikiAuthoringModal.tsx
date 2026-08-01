import { useMemo, useState } from 'react';
import type { AxiosError } from 'axios';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  AlertTriangle,
  BookOpen,
  Eye,
  FilePenLine,
  Info,
  Loader2,
  Save,
  Send,
  X,
} from 'lucide-react';

import { wikiAPI } from '../../api/client';
import type {
  WikiArticle,
  WikiCategory,
  WikiLanguage,
  WikiRevision,
} from '../../types/api';
import { translateApiError } from '../../utils/translateApiError';
import { ModalOverlay } from '../ModalOverlay';
import { toast } from '../Toast';


interface WikiAuthoringModalProps {
  categories: WikiCategory[];
  article?: WikiArticle | null;
  revision?: WikiRevision | null;
  onClose: () => void;
  onSaved: (revision: WikiRevision) => void;
}

type SubmitIntent = 'draft' | 'review';
type MobilePane = 'editor' | 'preview';

function languageFromInterface(value: string): WikiLanguage {
  if (value.startsWith('zh')) return 'zh';
  if (value.startsWith('en')) return 'en';
  return 'ru';
}

export function WikiAuthoringModal({
  categories,
  article = null,
  revision = null,
  onClose,
  onSaved,
}: WikiAuthoringModalProps) {
  const { t, i18n } = useTranslation();
  const existingContent = revision ?? article;
  const isNewArticle = !article && !revision;
  const [title, setTitle] = useState(existingContent?.title ?? '');
  const [summary, setSummary] = useState(existingContent?.summary ?? '');
  const [content, setContent] = useState(existingContent?.content ?? '');
  const [tags, setTags] = useState((existingContent?.tags ?? []).join(', '));
  const [editSummary, setEditSummary] = useState(revision?.edit_summary ?? '');
  const [categoryId, setCategoryId] = useState(
    revision?.article_category_id ?? article?.category_id ?? categories[0]?.id ?? 0,
  );
  const [language, setLanguage] = useState<WikiLanguage>(
    revision?.article_language
      ?? article?.language
      ?? languageFromInterface(i18n.resolvedLanguage ?? i18n.language),
  );
  const [mobilePane, setMobilePane] = useState<MobilePane>('editor');
  const [intent, setIntent] = useState<SubmitIntent | null>(null);
  const [discardPrompt, setDiscardPrompt] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const initialFingerprint = useMemo(
    () => JSON.stringify({ title, summary, content, tags, editSummary, categoryId, language }),
    [],
  );
  const currentFingerprint = JSON.stringify({
    title,
    summary,
    content,
    tags,
    editSummary,
    categoryId,
    language,
  });
  const dirty = initialFingerprint !== currentFingerprint;
  const busy = intent !== null;

  const parsedTags = tags
    .split(',')
    .map((tag) => tag.trim())
    .filter((tag, index, values) => tag && values.indexOf(tag) === index)
    .slice(0, 20);

  const requestClose = () => {
    if (busy) return;
    if (dirty) {
      setDiscardPrompt(true);
      return;
    }
    onClose();
  };

  const validate = (nextIntent: SubmitIntent): boolean => {
    if (!title.trim() || !summary.trim() || !content.trim() || !categoryId) {
      setValidationError(t('wikiAuthoring.validationRequired'));
      return false;
    }
    if (nextIntent === 'review' && !isNewArticle && !editSummary.trim()) {
      setValidationError(t('wikiAuthoring.validationEditSummary'));
      return false;
    }
    setValidationError(null);
    return true;
  };

  const save = async (nextIntent: SubmitIntent) => {
    if (!validate(nextIntent)) return;
    setIntent(nextIntent);
    try {
      let saved: WikiRevision;
      const revisionPayload = {
        title: title.trim(),
        summary: summary.trim(),
        content: content.trim(),
        tags: parsedTags.length ? parsedTags : null,
        edit_summary: editSummary.trim() || null,
      };

      if (revision) {
        saved = await wikiAPI.updateRevision(revision.id, revisionPayload);
      } else if (article) {
        saved = await wikiAPI.createRevision(article.id, revisionPayload);
      } else {
        saved = await wikiAPI.createAuthoredArticle({
          category_id: categoryId,
          space_key: 'knowledge',
          language,
          ...revisionPayload,
        });
      }

      if (nextIntent === 'review') {
        saved = await wikiAPI.submitRevision(saved.id, editSummary.trim() || null);
        toast.success(t('wikiAuthoring.submitted'));
      } else {
        toast.success(t('wikiAuthoring.draftSaved'));
      }
      onSaved(saved);
      onClose();
    } catch (error) {
      const apiError = error as AxiosError<{ detail?: unknown }>;
      toast.error(
        translateApiError(
          t,
          apiError.response?.data?.detail,
          t('wikiAuthoring.saveError'),
        ),
      );
    } finally {
      setIntent(null);
    }
  };

  const modalTitle = revision
    ? t('wikiAuthoring.editDraft')
    : article
      ? t('wikiAuthoring.proposeEdit')
      : t('wikiAuthoring.newArticle');

  return (
    <ModalOverlay
      onClose={requestClose}
      closeOnOverlayClick={false}
      closeOnEscape={false}
      contentClassName="min-h-full flex items-center justify-center p-3 md:p-6"
    >
      <div className="w-full max-w-7xl max-h-[94vh] overflow-hidden rounded-3xl border border-white/15 bg-[#111827] shadow-2xl shadow-purple-950/60">
        <header className="flex items-center justify-between gap-4 border-b border-white/10 bg-gradient-to-r from-blue-500/10 via-purple-500/10 to-transparent px-5 py-4 md:px-7">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-500/15 text-blue-300 ring-1 ring-blue-400/20">
              <FilePenLine className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <h2 className="truncate text-lg font-semibold text-white md:text-xl">{modalTitle}</h2>
              <p className="text-xs text-slate-400 md:text-sm">{t('wikiAuthoring.safePublication')}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={requestClose}
            disabled={busy}
            className="rounded-xl p-2 text-slate-400 transition hover:bg-white/10 hover:text-white disabled:opacity-40"
            aria-label={t('wikiAuthoring.close')}
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="grid max-h-[calc(94vh-148px)] overflow-y-auto lg:grid-cols-[minmax(0,1.05fr)_minmax(360px,0.95fr)] lg:overflow-hidden">
          <section className={`${mobilePane === 'preview' ? 'hidden lg:block' : 'block'} overflow-y-auto p-5 md:p-7`}>
            <div className="mb-5 flex rounded-xl border border-white/10 bg-white/5 p-1 lg:hidden">
              <button type="button" onClick={() => setMobilePane('editor')} className="flex-1 rounded-lg bg-blue-500 px-3 py-2 text-sm font-medium text-white">
                {t('wikiAuthoring.editor')}
              </button>
              <button type="button" onClick={() => setMobilePane('preview')} className="flex-1 rounded-lg px-3 py-2 text-sm text-slate-300">
                {t('wikiAuthoring.preview')}
              </button>
            </div>

            <div className="mb-5 flex items-start gap-3 rounded-2xl border border-cyan-400/15 bg-cyan-400/5 p-4 text-sm text-cyan-100/80">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-cyan-300" />
              <p>{isNewArticle ? t('wikiAuthoring.knowledgeNotice') : t('wikiAuthoring.revisionNotice')}</p>
            </div>

            <div className="grid gap-4 md:grid-cols-[1fr_180px]">
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-slate-200">{t('wikiAuthoring.title')}</span>
                <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} className="w-full rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-white outline-none transition placeholder:text-slate-600 focus:border-blue-400/70 focus:ring-2 focus:ring-blue-500/20" placeholder={t('wikiAuthoring.titlePlaceholder')} />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-slate-200">{t('wikiAuthoring.language')}</span>
                <select value={language} onChange={(event) => setLanguage(event.target.value as WikiLanguage)} disabled={!isNewArticle} className="w-full rounded-xl border border-white/15 bg-[#192235] px-4 py-3 text-white outline-none focus:border-blue-400/70 disabled:cursor-not-allowed disabled:opacity-60">
                  <option value="ru">Русский</option>
                  <option value="en">English</option>
                  <option value="zh">中文</option>
                </select>
              </label>
            </div>

            <label className="mt-4 block">
              <span className="mb-1.5 block text-sm font-medium text-slate-200">{t('wikiAuthoring.category')}</span>
              <select value={categoryId} onChange={(event) => setCategoryId(Number(event.target.value))} disabled={!isNewArticle} className="w-full rounded-xl border border-white/15 bg-[#192235] px-4 py-3 text-white outline-none focus:border-blue-400/70 disabled:cursor-not-allowed disabled:opacity-60">
                {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
              </select>
            </label>

            <label className="mt-4 block">
              <span className="mb-1.5 block text-sm font-medium text-slate-200">{t('wikiAuthoring.summary')}</span>
              <textarea value={summary} onChange={(event) => setSummary(event.target.value)} maxLength={1000} rows={3} className="w-full resize-y rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-white outline-none transition placeholder:text-slate-600 focus:border-blue-400/70 focus:ring-2 focus:ring-blue-500/20" placeholder={t('wikiAuthoring.summaryPlaceholder')} />
            </label>

            <label className="mt-4 block">
              <span className="mb-1.5 flex items-center justify-between gap-3 text-sm font-medium text-slate-200">
                {t('wikiAuthoring.content')}
                <span className="font-normal text-slate-500">Markdown</span>
              </span>
              <textarea value={content} onChange={(event) => setContent(event.target.value)} rows={16} className="w-full resize-y rounded-xl border border-white/15 bg-[#0b1220] px-4 py-3 font-mono text-sm leading-6 text-slate-200 outline-none transition placeholder:text-slate-600 focus:border-blue-400/70 focus:ring-2 focus:ring-blue-500/20" placeholder={t('wikiAuthoring.contentPlaceholder')} />
            </label>

            <label className="mt-4 block">
              <span className="mb-1.5 block text-sm font-medium text-slate-200">{t('wikiAuthoring.tags')}</span>
              <input value={tags} onChange={(event) => setTags(event.target.value)} className="w-full rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-white outline-none transition placeholder:text-slate-600 focus:border-blue-400/70 focus:ring-2 focus:ring-blue-500/20" placeholder={t('wikiAuthoring.tagsPlaceholder')} />
            </label>

            {!isNewArticle && (
              <label className="mt-4 block">
                <span className="mb-1.5 block text-sm font-medium text-slate-200">{t('wikiAuthoring.editSummary')}</span>
                <textarea value={editSummary} onChange={(event) => setEditSummary(event.target.value)} maxLength={1000} rows={2} className="w-full resize-y rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-white outline-none transition placeholder:text-slate-600 focus:border-blue-400/70 focus:ring-2 focus:ring-blue-500/20" placeholder={t('wikiAuthoring.editSummaryPlaceholder')} />
              </label>
            )}
          </section>

          <aside className={`${mobilePane === 'editor' ? 'hidden lg:flex' : 'flex'} min-h-[480px] flex-col border-l border-white/10 bg-[#0b1220]/80`}>
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-4 md:px-7">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-200"><Eye className="h-4 w-4 text-purple-300" />{t('wikiAuthoring.preview')}</div>
              <button type="button" onClick={() => setMobilePane('editor')} className="rounded-lg px-3 py-1.5 text-xs text-slate-400 hover:bg-white/10 hover:text-white lg:hidden">{t('wikiAuthoring.backToEditor')}</button>
            </div>
            <div className="flex-1 overflow-y-auto p-5 md:p-7">
              <div className="mb-5 border-b border-white/10 pb-5">
                <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-blue-500/10 px-3 py-1 text-xs text-blue-300"><BookOpen className="h-3.5 w-3.5" />{t('wikiAuthoring.knowledgeBase')}</div>
                <h3 className="text-2xl font-bold leading-tight text-white">{title || t('wikiAuthoring.untitled')}</h3>
                {summary && <p className="mt-3 text-sm leading-6 text-slate-400">{summary}</p>}
              </div>
              {content ? (
                <div className="prose prose-invert max-w-none break-words text-slate-200 [&_a]:text-blue-400 [&_blockquote]:border-l-4 [&_blockquote]:border-blue-500 [&_blockquote]:bg-blue-500/5 [&_blockquote]:px-4 [&_code]:rounded [&_code]:bg-black/40 [&_code]:px-1.5 [&_code]:py-0.5 [&_h1]:text-white [&_h2]:text-white [&_h3]:text-white [&_li]:marker:text-blue-400 [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:bg-black/50 [&_pre]:p-4">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                </div>
              ) : (
                <div className="rounded-2xl border border-dashed border-white/15 px-5 py-12 text-center text-sm text-slate-500">{t('wikiAuthoring.previewEmpty')}</div>
              )}
            </div>
          </aside>
        </div>

        <footer className="border-t border-white/10 bg-[#111827] px-5 py-4 md:px-7">
          {validationError && <div className="mb-3 flex items-center gap-2 text-sm text-amber-300"><AlertTriangle className="h-4 w-4" />{validationError}</div>}
          {discardPrompt ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-amber-200">{t('wikiAuthoring.discardQuestion')}</p>
              <div className="flex gap-2">
                <button type="button" onClick={() => setDiscardPrompt(false)} className="rounded-xl border border-white/15 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/5">{t('wikiAuthoring.keepEditing')}</button>
                <button type="button" onClick={onClose} className="rounded-xl bg-red-500/15 px-4 py-2.5 text-sm font-medium text-red-200 ring-1 ring-red-400/25 hover:bg-red-500/25">{t('wikiAuthoring.discard')}</button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs leading-5 text-slate-500">{t('wikiAuthoring.publicationHint')}</p>
              <div className="flex shrink-0 gap-2">
                <button type="button" onClick={() => save('draft')} disabled={busy} className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/15 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:bg-white/5 disabled:opacity-50">
                  {intent === 'draft' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}{t('wikiAuthoring.saveDraft')}
                </button>
                <button type="button" onClick={() => save('review')} disabled={busy} className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-500 to-purple-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-purple-950/40 transition hover:brightness-110 disabled:opacity-50">
                  {intent === 'review' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}{t('wikiAuthoring.sendForReview')}
                </button>
              </div>
            </div>
          )}
        </footer>
      </div>
    </ModalOverlay>
  );
}
