/** Компонент для управления обратной связью от пользователей */

import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useDropzone } from 'react-dropzone';
import {
  ArrowLeft,
  Bug,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  FileText,
  HelpCircle,
  ImagePlus,
  Lightbulb,
  MessageCircle,
  MessageSquare,
  RefreshCw,
  Search,
  Send,
  SmilePlus,
  Trash2,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { AxiosError } from 'axios';
import { adminFeedbackAPI } from '../../api/client';
import { downloadBlob } from '../../utils/download';
import type { Feedback, FeedbackDetail, FeedbackStatus, FeedbackType } from '../../types/api';
import { toast } from '../Toast';
import { ConfirmDeleteModal } from '../ConfirmDeleteModal';
import { FeedbackImages } from '../FeedbackImages';
import { translateApiError } from '../../utils/translateApiError';
import { createIdempotencyKey } from '../../utils/idempotencyKey';
import { formatMediumDateTime } from '../../utils/formatDate';
import { useDebounce } from '../../hooks/useDebounce';

const RESPONSE_EMOJIS = [
  '😀', '😄', '🙂', '😊', '😉', '🤔',
  '👍', '👎', '👏', '🙏', '🎉', '✅',
  '⚠️', '❤️', '🔥', '🚀', '🧵', '🛠️',
] as const;

const PAGE_SIZE = 30;
const MAX_REPLY_IMAGES = 4;
const MAX_REPLY_IMAGE_BYTES = 8 * 1024 * 1024;
const REPLY_IMAGE_TYPES = {
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/webp': ['.webp'],
};

const STATUS_STYLES: Record<FeedbackStatus, { dot: string; text: string }> = {
  open: { dot: 'bg-amber-400', text: 'text-amber-300' },
  in_progress: { dot: 'bg-sky-400', text: 'text-sky-300' },
  resolved: { dot: 'bg-emerald-400', text: 'text-emerald-300' },
  closed: { dot: 'bg-gray-500', text: 'text-gray-400' },
};

const TYPE_ICONS: Record<FeedbackType, typeof Bug> = {
  bug: Bug,
  feature: Lightbulb,
  question: HelpCircle,
  other: MessageSquare,
};

const TYPE_LABEL_KEYS: Record<FeedbackType, string> = {
  bug: 'adminFeedback.filter_bug',
  feature: 'adminFeedback.filter_feature',
  question: 'adminFeedback.filter_question',
  other: 'adminFeedback.filter_other',
};

const STATUS_LABEL_KEYS: Record<FeedbackStatus, string> = {
  open: 'adminFeedback.filter_open',
  in_progress: 'adminFeedback.filter_in_progress',
  resolved: 'adminFeedback.filter_resolved',
  closed: 'adminFeedback.filter_closed',
};

// Older accounts have no recorded language, so the script of the text decides.
function feedbackLanguage(feedback: Feedback): string | null {
  const recorded = feedback.user_language?.trim().slice(0, 2);
  if (recorded) return recorded.toUpperCase();
  const text = `${feedback.subject} ${feedback.message}`;
  if (/[Ѐ-ӿ]/.test(text)) return 'RU';
  if (/[一-鿿]/.test(text)) return 'ZH';
  if (/[A-Za-z]/.test(text)) return 'EN';
  return null;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
}

function ReplyImageChip({ file, onRemove }: { file: File; onRemove: () => void }) {
  const { t } = useTranslation();
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  return (
    <div className="group relative h-16 w-16 shrink-0 overflow-hidden rounded-lg border border-white/15 bg-black/30">
      {preview && <img src={preview} alt="" className="h-full w-full object-cover" />}
      <button
        type="button"
        onClick={onRemove}
        aria-label={t('adminFeedback.removeImage', { name: file.name })}
        className="absolute right-0.5 top-0.5 grid h-5 w-5 place-items-center rounded-full bg-black/70 text-gray-200 transition hover:bg-red-500 hover:text-white"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}

export function AdminFeedback() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedStatus, setSelectedStatus] = useState<FeedbackStatus | 'all'>('all');
  const [selectedType, setSelectedType] = useState<FeedbackType | 'all'>('all');
  const [awaitingOnly, setAwaitingOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [selectedFeedback, setSelectedFeedback] = useState<Feedback | null>(null);
  const [adminResponse, setAdminResponse] = useState('');
  const [replyImages, setReplyImages] = useState<File[]>([]);
  const [replyIdempotencyKey, setReplyIdempotencyKey] = useState(createIdempotencyKey);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isEmojiPickerOpen, setIsEmojiPickerOpen] = useState(false);
  const [isPluginLogOpen, setIsPluginLogOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const responseTextareaRef = useRef<HTMLTextAreaElement>(null);
  const emojiPickerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const selectedIdRef = useRef<number | null>(null);
  selectedIdRef.current = selectedFeedback?.id ?? null;
  const debouncedSearch = useDebounce(searchQuery.trim(), 300);

  useEffect(() => {
    if (!isEmojiPickerOpen) return;

    const closeOnOutsidePointer = (event: PointerEvent) => {
      if (!emojiPickerRef.current?.contains(event.target as Node)) {
        setIsEmojiPickerOpen(false);
      }
    };

    document.addEventListener('pointerdown', closeOnOutsidePointer);
    return () => document.removeEventListener('pointerdown', closeOnOutsidePointer);
  }, [isEmojiPickerOpen]);

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return;
      if (isEditableTarget(event.target) || document.querySelector('[aria-modal="true"]')) return;
      event.preventDefault();
      searchInputRef.current?.focus();
    };
    document.addEventListener('keydown', focusSearch);
    return () => document.removeEventListener('keydown', focusSearch);
  }, []);

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ['admin-feedback', selectedStatus, selectedType, awaitingOnly, debouncedSearch, page],
    queryFn: ({ signal }) => adminFeedbackAPI.list({
      page,
      size: PAGE_SIZE,
      status: selectedStatus === 'all' ? undefined : selectedStatus,
      type: selectedType === 'all' ? undefined : selectedType,
      search: debouncedSearch || undefined,
      awaiting_reply: awaitingOnly || undefined,
      sort: 'attention',
    }, signal),
    placeholderData: keepPreviousData,
  });

  const selectedFeedbackQuery = useQuery({
    queryKey: ['admin-feedback-detail', selectedFeedback?.id],
    queryFn: () => adminFeedbackAPI.get(selectedFeedback!.id),
    enabled: selectedFeedback !== null,
  });

  const latestMessageId = selectedFeedbackQuery.data?.messages.at(-1)?.id;
  useEffect(() => {
    const container = messagesRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [selectedFeedback?.id, latestMessageId]);

  const pluginLogQuery = useQuery({
    queryKey: ['admin-feedback-plugin-log', selectedFeedback?.id],
    queryFn: async () => (await adminFeedbackAPI.downloadPluginLog(selectedFeedback!.id)).text(),
    enabled: isPluginLogOpen && selectedFeedback !== null,
    staleTime: Infinity,
  });

  const cacheDetail = (updatedFeedback: FeedbackDetail) => {
    queryClient.setQueryData(['admin-feedback-detail', updatedFeedback.id], updatedFeedback);
    queryClient.invalidateQueries({ queryKey: ['admin-feedback'] });
    queryClient.invalidateQueries({ queryKey: ['admin-communications-unread-count'] });
  };

  const markReadMutation = useMutation({
    mutationFn: ({ id, throughMessageId }: { id: number; throughMessageId: number }) =>
      adminFeedbackAPI.markRead(id, throughMessageId),
    onSuccess: cacheDetail,
  });

  useEffect(() => {
    const detail = selectedFeedbackQuery.data;
    if (!detail || (detail.admin_unread_count ?? 0) <= 0 || markReadMutation.isPending) return;
    const throughMessageId = Math.max(
      0,
      ...detail.messages
        .filter((message) => message.author_type === 'user')
        .map((message) => message.id),
    );
    if (throughMessageId > 0) {
      markReadMutation.mutate({ id: detail.id, throughMessageId });
    }
  }, [selectedFeedbackQuery.data, markReadMutation.isPending]);

  const replyMutation = useMutation({
    mutationFn: ({
      id,
      response,
      images,
      idempotencyKey,
    }: {
      id: number;
      response: string;
      images: File[];
      idempotencyKey: string;
    }) => adminFeedbackAPI.reply(id, { message: response, images, idempotency_key: idempotencyKey }),
    onSuccess: (updatedFeedback) => {
      cacheDetail(updatedFeedback);
      toast.success(t('adminFeedback.replySent'));
      // The admin may have moved to another thread while the upload was running.
      if (selectedIdRef.current !== updatedFeedback.id) return;
      setSelectedFeedback(updatedFeedback);
      setAdminResponse('');
      setReplyImages([]);
      setIsEmojiPickerOpen(false);
      setReplyIdempotencyKey(createIdempotencyKey());
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, error?.response?.data?.detail, t('adminFeedback.updateError')));
    },
  });

  // Статус живёт отдельно от ответа: «взял в работу» не должно требовать письма
  // человеку, а отправка письма не должна втихую менять статус.
  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: FeedbackStatus }) =>
      adminFeedbackAPI.update(id, { status }),
    onSuccess: (updatedFeedback) => {
      cacheDetail(updatedFeedback);
      if (selectedIdRef.current === updatedFeedback.id) setSelectedFeedback(updatedFeedback);
      toast.success(t('adminFeedback.statusSaved'));
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, error?.response?.data?.detail, t('adminFeedback.updateError')));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => adminFeedbackAPI.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-feedback'] });
      queryClient.invalidateQueries({ queryKey: ['admin-communications-unread-count'] });
      closeFeedback();
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, error?.response?.data?.detail, t('adminFeedback.deleteError')));
    },
  });

  const addReplyImages = useCallback((files: File[]) => {
    setReplyImages((current) => {
      const next = [...current, ...files];
      if (next.length > MAX_REPLY_IMAGES) {
        toast.warning(t('adminFeedback.imagesLimit', { count: MAX_REPLY_IMAGES }));
      }
      return next.slice(0, MAX_REPLY_IMAGES);
    });
  }, [t]);

  const { getRootProps, getInputProps, isDragActive, open: openImagePicker } = useDropzone({
    accept: REPLY_IMAGE_TYPES,
    maxSize: MAX_REPLY_IMAGE_BYTES,
    multiple: true,
    noClick: true,
    noKeyboard: true,
    onDropAccepted: addReplyImages,
    onDropRejected: () => toast.warning(t('adminFeedback.imageRejected')),
  });

  const openFeedback = (feedback: Feedback) => {
    if (selectedFeedback?.id === feedback.id) return;
    setSelectedFeedback(feedback);
    setAdminResponse('');
    setReplyImages([]);
    setReplyIdempotencyKey(createIdempotencyKey());
    setIsEmojiPickerOpen(false);
    setIsPluginLogOpen(false);
  };

  const closeFeedback = () => {
    setSelectedFeedback(null);
    setAdminResponse('');
    setReplyImages([]);
    setIsEmojiPickerOpen(false);
    setIsPluginLogOpen(false);
  };

  const canSend = Boolean(adminResponse.trim() || replyImages.length) && !replyMutation.isPending;

  const sendReply = () => {
    if (!selectedFeedback || !canSend) return;
    replyMutation.mutate({
      id: selectedFeedback.id,
      response: adminResponse.trim(),
      images: replyImages,
      idempotencyKey: replyIdempotencyKey,
    });
  };

  const insertEmoji = (emoji: string) => {
    const textarea = responseTextareaRef.current;
    const selectionStart = textarea?.selectionStart ?? adminResponse.length;
    const selectionEnd = textarea?.selectionEnd ?? selectionStart;
    const nextResponse = `${adminResponse.slice(0, selectionStart)}${emoji}${adminResponse.slice(selectionEnd)}`;
    const nextCursorPosition = selectionStart + emoji.length;

    setAdminResponse(nextResponse);
    requestAnimationFrame(() => {
      textarea?.focus();
      textarea?.setSelectionRange(nextCursorPosition, nextCursorPosition);
    });
  };

  const resetToFirstPage = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value);
    setPage(1);
  };

  const moveListFocus = (from: HTMLElement, step: number) => {
    const rows = Array.from(listRef.current?.querySelectorAll<HTMLButtonElement>('[data-feedback-row]') ?? []);
    const index = rows.indexOf(from as HTMLButtonElement);
    const next = rows[index === -1 ? 0 : Math.min(rows.length - 1, Math.max(0, index + step))];
    next?.focus();
    next?.scrollIntoView({ block: 'nearest' });
  };

  const handleListKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'j') {
      event.preventDefault();
      moveListFocus(event.target as HTMLElement, 1);
    } else if (event.key === 'ArrowUp' || event.key === 'k') {
      event.preventDefault();
      moveListFocus(event.target as HTMLElement, -1);
    }
  };

  const handleRootKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    // Portaled dialogs bubble React events here but handle their own Escape.
    if (event.key !== 'Escape' || !event.currentTarget.contains(event.target as Node)) return;
    if (isEmojiPickerOpen) {
      event.preventDefault();
      setIsEmojiPickerOpen(false);
      responseTextareaRef.current?.focus();
      return;
    }
    if (event.target === searchInputRef.current) {
      searchInputRef.current?.blur();
      return;
    }
    if (event.target === responseTextareaRef.current) {
      responseTextareaRef.current?.blur();
      return;
    }
    if (selectedFeedback) {
      const closedId = selectedFeedback.id;
      closeFeedback();
      requestAnimationFrame(() => {
        listRef.current
          ?.querySelector<HTMLButtonElement>(`[data-feedback-row="${closedId}"]`)
          ?.focus();
      });
    }
  };

  const shortDate = useMemo(
    () => new Intl.DateTimeFormat(i18n.language, { day: 'numeric', month: 'short' }),
    [i18n.language],
  );

  const feedbackItems = data?.items ?? [];
  const total = data?.total ?? 0;
  const pages = data?.pages ?? 0;
  const selectedFeedbackView = selectedFeedbackQuery.data ?? selectedFeedback;
  const threadMessages = selectedFeedbackQuery.data?.messages ?? (
    selectedFeedback
      ? [{
          id: `initial-${selectedFeedback.id}`,
          author_type: 'user' as const,
          message: selectedFeedback.message,
          created_at: selectedFeedback.created_at,
          attachments: [],
        }]
      : []
  );
  const selectClass = 'rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-purple-500';

  const renderList = () => {
    if (isLoading) {
      return <div className="grid min-h-64 place-items-center text-sm text-gray-400">{t('adminFeedback.loading')}</div>;
    }
    if (error) {
      return <div className="grid min-h-64 place-items-center text-sm text-red-300">{t('adminFeedback.error')}</div>;
    }
    if (feedbackItems.length === 0) {
      return (
        <div className="grid min-h-64 place-items-center px-6 text-center text-sm text-gray-400">
          {debouncedSearch || awaitingOnly || selectedStatus !== 'all' || selectedType !== 'all'
            ? t('adminFeedback.no_feedback_found')
            : t('adminFeedback.no_feedback_yet')}
        </div>
      );
    }
    return (
      <div ref={listRef} onKeyDown={handleListKeyDown} className="max-h-[70vh] min-h-0 overflow-y-auto custom-scrollbar lg:max-h-none lg:flex-1">
        {feedbackItems.map((feedback) => {
          const TypeIcon = TYPE_ICONS[feedback.type];
          const unread = feedback.admin_unread_count ?? 0;
          const language = feedbackLanguage(feedback);
          const selected = selectedFeedback?.id === feedback.id;
          return (
            <button
              key={feedback.id}
              type="button"
              data-feedback-row={feedback.id}
              onClick={() => openFeedback(feedback)}
              className={`relative block w-full border-b border-white/5 px-3 py-2 text-left transition focus:outline-none focus-visible:bg-white/10 ${
                selected ? 'bg-purple-500/15' : 'hover:bg-white/5'
              }`}
            >
              {feedback.awaiting_reply && (
                <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-amber-400" aria-hidden="true" />
              )}
              <div className="flex items-center gap-2">
                <span className="shrink-0 font-mono text-xs font-semibold text-purple-300/90">#{feedback.id}</span>
                <TypeIcon className="h-3.5 w-3.5 shrink-0 text-gray-500" aria-label={t(TYPE_LABEL_KEYS[feedback.type])} />
                <span className={`min-w-0 flex-1 truncate text-sm ${unread || feedback.awaiting_reply ? 'font-semibold text-white' : 'text-gray-200'}`}>
                  {feedback.subject}
                </span>
                {unread > 0 && (
                  <span className="grid h-4 min-w-4 shrink-0 place-items-center rounded-full bg-cyan-400 px-1 text-[10px] font-bold text-slate-950">
                    {unread}
                  </span>
                )}
                <span className="shrink-0 text-[11px] text-gray-500">{shortDate.format(new Date(feedback.updated_at))}</span>
              </div>
              <div className="mt-0.5 flex items-center gap-1.5 pl-0.5 text-[11px] text-gray-500">
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${STATUS_STYLES[feedback.status].dot}`} aria-hidden="true" />
                <span className={`shrink-0 ${STATUS_STYLES[feedback.status].text}`}>{t(STATUS_LABEL_KEYS[feedback.status])}</span>
                {feedback.awaiting_reply && (
                  <span className="shrink-0 text-amber-300">· {t('adminFeedback.awaiting')}</span>
                )}
                <span className="shrink-0">· {feedback.user_id ? (feedback.user_username || t('adminFeedback.user')) : t('adminFeedback.anonymous')}</span>
                {language && <span className="shrink-0 font-medium text-gray-400">· {language}</span>}
                <span className="min-w-0 truncate">· {feedback.message}</span>
              </div>
            </button>
          );
        })}
      </div>
    );
  };

  const renderThread = () => {
    if (!selectedFeedbackView) {
      return (
        <div className="grid h-full min-h-[480px] place-items-center px-6 text-center lg:min-h-0">
          <div>
            <MessageCircle className="mx-auto mb-3 h-10 w-10 text-gray-600" />
            <p className="font-medium text-gray-300">{t('adminFeedback.selectThread')}</p>
            <p className="mt-2 text-xs text-gray-500">{t('adminFeedback.keyboardHint')}</p>
          </div>
        </div>
      );
    }

    const TypeIcon = TYPE_ICONS[selectedFeedbackView.type];
    const language = feedbackLanguage(selectedFeedbackView);
    const logSize = selectedFeedbackView.plugin_log_size;

    const pluginLogBlock = logSize ? (
      <div className="rounded-lg border border-white/10 bg-white/5 text-sm text-gray-300">
        <div className="flex items-center gap-2 px-3 py-1.5">
          <FileText className="h-4 w-4 shrink-0 text-gray-400" />
          <span className="min-w-0 flex-1 truncate text-xs">
            {t('adminFeedback.pluginLog', { size: Math.max(1, Math.round(logSize / 1024)) })}
          </span>
          <button
            type="button"
            onClick={() => setIsPluginLogOpen((open) => !open)}
            aria-expanded={isPluginLogOpen}
            className="shrink-0 rounded-md border border-white/15 px-2 py-0.5 text-xs text-gray-200 transition hover:bg-white/10 hover:text-white"
          >
            {isPluginLogOpen ? t('adminFeedback.hidePluginLog') : t('adminFeedback.showPluginLog')}
          </button>
          <button
            type="button"
            onClick={() => {
              const feedbackId = selectedFeedbackView.id;
              adminFeedbackAPI
                .downloadPluginLog(feedbackId)
                .then((blob) => downloadBlob(blob, `feedback-${feedbackId}-plugin.log`))
                .catch(() => toast.error(t('adminFeedback.pluginLogDownloadError')));
            }}
            aria-label={t('adminFeedback.downloadPluginLog')}
            title={t('adminFeedback.downloadPluginLog')}
            className="shrink-0 rounded-md border border-white/15 p-1 text-gray-200 transition hover:bg-white/10 hover:text-white"
          >
            <Download className="h-3.5 w-3.5" />
          </button>
        </div>
        {isPluginLogOpen && (
          <div className="border-t border-white/10">
            {pluginLogQuery.isLoading ? (
              <p className="px-3 py-2 text-xs text-gray-400">{t('adminFeedback.loading')}</p>
            ) : pluginLogQuery.isError ? (
              <p className="px-3 py-2 text-xs text-red-300">{t('adminFeedback.pluginLogLoadError')}</p>
            ) : (
              <pre className="max-h-72 overflow-auto whitespace-pre px-3 py-2 font-mono text-[11px] leading-5 text-gray-300 custom-scrollbar">
                {pluginLogQuery.data}
              </pre>
            )}
          </div>
        )}
      </div>
    ) : null;

    return (
      <div className="flex h-full min-h-[480px] flex-col lg:min-h-0">
        <header className="border-b border-white/10 px-4 py-3">
          <div className="flex items-start gap-2">
            <button
              type="button"
              onClick={closeFeedback}
              aria-label={t('adminFeedback.back')}
              className="mt-0.5 rounded-lg p-1 text-gray-400 hover:bg-white/10 hover:text-white lg:hidden"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-gray-400">
                <span className="font-mono text-sm font-semibold text-purple-200">#{selectedFeedbackView.id}</span>
                <span className="inline-flex items-center gap-1">
                  <TypeIcon className="h-3.5 w-3.5" />
                  {t(TYPE_LABEL_KEYS[selectedFeedbackView.type])}
                </span>
                <span>·</span>
                <span>
                  {selectedFeedbackView.user_id
                    ? (selectedFeedbackView.user_username || t('adminFeedback.user'))
                    : `${t('adminFeedback.anonymous')}${selectedFeedbackView.email ? ` · ${selectedFeedbackView.email}` : ''}`}
                </span>
                {language && (
                  <span title={t('adminFeedback.languageTitle')} className="rounded border border-white/10 px-1 text-[10px] font-semibold text-gray-300">
                    {language}
                  </span>
                )}
                <span>· {formatMediumDateTime(selectedFeedbackView.created_at)}</span>
                {selectedFeedbackView.source_url && (
                  <a
                    href={selectedFeedbackView.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-0.5 text-purple-300 hover:text-purple-200"
                  >
                    {t('adminFeedback.sourcePage')}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>
              <h3 className="mt-1 break-words text-base font-semibold text-white">{selectedFeedbackView.subject}</h3>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <select
                value={selectedFeedbackView.status}
                disabled={statusMutation.isPending}
                title={t('adminFeedback.statusReplyHint')}
                aria-label={t('adminFeedback.modal_change_status')}
                onChange={(event) => statusMutation.mutate({
                  id: selectedFeedbackView.id,
                  status: event.target.value as FeedbackStatus,
                })}
                className={`${selectClass} disabled:opacity-60`}
              >
                {(Object.keys(STATUS_LABEL_KEYS) as FeedbackStatus[]).map((status) => (
                  <option key={status} value={status}>{t(STATUS_LABEL_KEYS[status])}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(true)}
                disabled={deleteMutation.isPending}
                aria-label={t('adminFeedback.deleteButton')}
                title={t('adminFeedback.deleteButton')}
                className="rounded-lg border border-white/10 p-1.5 text-gray-400 transition hover:border-red-400/40 hover:bg-red-500/15 hover:text-red-300 disabled:opacity-50"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>
        </header>

        <div ref={messagesRef} className="max-h-[52vh] min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3 custom-scrollbar lg:max-h-none">
          {threadMessages.map((threadMessage, index) => {
            const fromAdmin = threadMessage.author_type === 'admin';
            return (
              <Fragment key={threadMessage.id}>
                <div className={`flex ${fromAdmin ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] ${fromAdmin ? 'flex flex-col items-end' : ''}`}>
                    <div className={`mb-0.5 text-[11px] ${fromAdmin ? 'text-purple-300' : 'text-cyan-300'}`}>
                      {fromAdmin ? t('adminFeedback.you') : t('adminFeedback.user')}
                      {' · '}
                      {formatMediumDateTime(threadMessage.created_at)}
                    </div>
                    {threadMessage.message && (
                      <div
                        className={`whitespace-pre-wrap break-words rounded-xl border px-3 py-2 text-sm leading-6 text-gray-200 ${
                          fromAdmin
                            ? 'rounded-tr-sm border-purple-400/25 bg-purple-500/10'
                            : 'rounded-tl-sm border-cyan-400/20 bg-cyan-500/10'
                        }`}
                      >
                        {threadMessage.message}
                      </div>
                    )}
                    <FeedbackImages attachments={threadMessage.attachments} />
                  </div>
                </div>
                {index === 0 && pluginLogBlock}
              </Fragment>
            );
          })}

        </div>

        <div
          {...getRootProps({
            className: `relative border-t border-white/10 px-4 py-3 transition ${
              isDragActive ? 'bg-purple-500/10 ring-2 ring-inset ring-purple-400/60' : ''
            }`,
          })}
        >
          <input {...getInputProps()} />
          {isDragActive && (
            <div className="pointer-events-none absolute inset-0 grid place-items-center text-sm font-medium text-purple-200">
              {t('adminFeedback.dropImages')}
            </div>
          )}
          <textarea
            ref={responseTextareaRef}
            value={adminResponse}
            onChange={(event) => setAdminResponse(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                event.preventDefault();
                sendReply();
              }
            }}
            onPaste={(event) => {
              const files = Array.from(event.clipboardData.files);
              if (!files.length) return;
              event.preventDefault();
              const images = files.filter(
                (file) => file.type in REPLY_IMAGE_TYPES && file.size <= MAX_REPLY_IMAGE_BYTES,
              );
              if (images.length < files.length) toast.warning(t('adminFeedback.imageRejected'));
              if (images.length) addReplyImages(images);
            }}
            rows={3}
            placeholder={t('adminFeedback.modal_response_placeholder')}
            className="w-full resize-y rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-purple-500 custom-scrollbar"
          />
          {replyImages.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {replyImages.map((file, index) => (
                <ReplyImageChip
                  key={`${file.name}-${file.lastModified}-${index}`}
                  file={file}
                  onRemove={() => setReplyImages((current) => current.filter((item) => item !== file))}
                />
              ))}
            </div>
          )}
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={openImagePicker}
              disabled={replyImages.length >= MAX_REPLY_IMAGES}
              title={t('adminFeedback.attachHint')}
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-gray-300 transition hover:bg-white/10 hover:text-white disabled:opacity-40"
            >
              <ImagePlus className="h-4 w-4" />
              {t('adminFeedback.attachImages')}
              {replyImages.length > 0 && <span className="text-gray-500">{replyImages.length}/{MAX_REPLY_IMAGES}</span>}
            </button>
            <div ref={emojiPickerRef} className="relative">
              <button
                type="button"
                aria-label={t('adminFeedback.addEmoji')}
                aria-haspopup="dialog"
                aria-expanded={isEmojiPickerOpen}
                aria-controls="admin-feedback-emoji-picker"
                onClick={() => setIsEmojiPickerOpen((isOpen) => !isOpen)}
                className="grid h-8 w-8 place-items-center rounded-lg border border-white/10 text-gray-400 transition hover:bg-white/10 hover:text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                <SmilePlus className="h-4 w-4" />
              </button>
              {isEmojiPickerOpen && (
                <div
                  id="admin-feedback-emoji-picker"
                  role="dialog"
                  aria-label={t('adminFeedback.emojiPicker')}
                  className="absolute bottom-full left-0 z-30 mb-2 grid w-56 grid-cols-6 gap-1 rounded-xl border border-white/15 bg-gray-950/95 p-2 shadow-2xl shadow-black/50 backdrop-blur-md"
                >
                  {RESPONSE_EMOJIS.map((emoji) => (
                    <button
                      key={emoji}
                      type="button"
                      aria-label={t('adminFeedback.insertEmoji', { emoji })}
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => insertEmoji(emoji)}
                      className="flex h-8 w-8 items-center justify-center rounded-lg text-lg transition hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    >
                      {emoji}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <span className="ml-auto hidden text-[11px] text-gray-500 sm:inline">{t('adminFeedback.sendHint')}</span>
            <button
              type="button"
              onClick={sendReply}
              disabled={!canSend}
              className="inline-flex items-center gap-1.5 rounded-lg bg-purple-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-50 max-sm:ml-auto"
            >
              {replyMutation.isPending ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              {replyMutation.isPending ? t('adminFeedback.sending') : t('adminFeedback.send')}
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div onKeyDown={handleRootKeyDown} className="overflow-hidden rounded-2xl border border-white/10 bg-[#121226]/70">
      <div className="flex flex-wrap items-center gap-2 border-b border-white/10 px-3 py-2.5 md:px-4">
        <div className="mr-1 flex items-center gap-2">
          <MessageCircle className="h-4 w-4 text-purple-300" />
          <h2 className="text-sm font-semibold text-white">{t('adminFeedback.title')}</h2>
          <span className="text-xs text-gray-500">{total}</span>
        </div>
        <div className="relative min-w-[12rem] flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
          <input
            ref={searchInputRef}
            type="search"
            value={searchQuery}
            onChange={(event) => {
              setSearchQuery(event.target.value);
              setPage(1);
            }}
            placeholder={t('adminFeedback.search_placeholder')}
            aria-label={t('adminFeedback.search_placeholder')}
            className="w-full rounded-lg border border-white/10 bg-white/5 py-1.5 pl-8 pr-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>
        <button
          type="button"
          aria-pressed={awaitingOnly}
          onClick={() => {
            setAwaitingOnly((value) => !value);
            setPage(1);
          }}
          className={`rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${
            awaitingOnly
              ? 'border-amber-400/40 bg-amber-400/15 text-amber-200'
              : 'border-white/10 bg-white/5 text-gray-300 hover:bg-white/10 hover:text-white'
          }`}
        >
          {t('adminFeedback.awaitingOnly')}
        </button>
        <select
          value={selectedStatus}
          onChange={(event) => resetToFirstPage(setSelectedStatus)(event.target.value as FeedbackStatus | 'all')}
          aria-label={t('adminFeedback.filter_all_statuses')}
          className={selectClass}
        >
          <option value="all">{t('adminFeedback.filter_all_statuses')}</option>
          {(Object.keys(STATUS_LABEL_KEYS) as FeedbackStatus[]).map((status) => (
            <option key={status} value={status}>{t(STATUS_LABEL_KEYS[status])}</option>
          ))}
        </select>
        <select
          value={selectedType}
          onChange={(event) => resetToFirstPage(setSelectedType)(event.target.value as FeedbackType | 'all')}
          aria-label={t('adminFeedback.filter_all_types')}
          className={selectClass}
        >
          <option value="all">{t('adminFeedback.filter_all_types')}</option>
          {(Object.keys(TYPE_LABEL_KEYS) as FeedbackType[]).map((type) => (
            <option key={type} value={type}>{t(TYPE_LABEL_KEYS[type])}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => refetch()}
          aria-label={t('adminFeedback.refresh')}
          title={t('adminFeedback.refresh')}
          className="ml-auto rounded-lg border border-white/10 bg-white/5 p-1.5 text-gray-400 transition hover:bg-white/10 hover:text-white"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="grid lg:h-[min(78vh,860px)] lg:grid-cols-[minmax(300px,0.9fr)_minmax(0,1.6fr)]">
        <aside className={`${selectedFeedback ? 'hidden lg:flex' : 'flex'} min-h-0 min-w-0 flex-col border-white/10 lg:border-r`}>
          {renderList()}
          {pages > 1 && (
            <div className="flex items-center justify-center gap-2 border-t border-white/10 px-3 py-2 text-xs text-gray-400">
              <button
                type="button"
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                disabled={page === 1}
                aria-label={t('adminFeedback.pagination_back')}
                className="rounded-md p-1 hover:bg-white/10 hover:text-white disabled:opacity-40"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span>{t('adminFeedback.pagination_page_info', { page, pages })}</span>
              <button
                type="button"
                onClick={() => setPage((current) => Math.min(pages, current + 1))}
                disabled={page >= pages}
                aria-label={t('adminFeedback.pagination_forward')}
                className="rounded-md p-1 hover:bg-white/10 hover:text-white disabled:opacity-40"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </aside>
        <section className={`${selectedFeedback ? 'block' : 'hidden lg:block'} min-h-0 min-w-0`}>
          {renderThread()}
        </section>
      </div>

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
