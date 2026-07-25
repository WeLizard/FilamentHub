import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Archive,
  ArrowLeft,
  Building2,
  Check,
  CheckCircle2,
  CheckCheck,
  Clock3,
  Download,
  Inbox,
  Mail,
  MailPlus,
  MessageCircle,
  Paperclip,
  RefreshCw,
  Reply,
  Send,
  Trash2,
  TriangleAlert,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { AxiosError } from 'axios';
import { adminCommunicationsAPI } from '../../api/client';
import type {
  EmailDeliveryStatus,
  EmailMessage,
  EmailSenderProfile,
  EmailThreadDetail,
  EmailThreadStatus,
} from '../../types/api';
import { translateApiError } from '../../utils/translateApiError';
import { downloadBlob } from '../../utils/download';
import { toast } from '../Toast';
import { ModalOverlay } from '../ModalOverlay';
import { ConfirmModal } from '../ConfirmModal';
import { AdminFeedback } from './AdminFeedback';
import { AdminNotificationCampaigns } from './AdminNotificationCampaigns';
import { EmailComposer, type EmailComposerValue } from './EmailComposer';

type CommunicationSection = 'inbox' | 'feedback' | 'broadcasts';
type ThreadFilter = 'all' | EmailThreadStatus;
type IdempotencyState = { fingerprint: string; key: string };

const emptyEmailComposerValue = (): EmailComposerValue => ({
  text: '',
  html: '',
  attachments: [],
});

const idempotencyKeyFor = (
  state: React.MutableRefObject<IdempotencyState>,
  fingerprint: string,
): string => {
  if (state.current.fingerprint !== fingerprint) {
    state.current = { fingerprint, key: crypto.randomUUID() };
  }
  return state.current.key;
};

const emailDraftFingerprint = (
  fields: unknown[],
  draft: EmailComposerValue,
): string => JSON.stringify([
  ...fields,
  draft.text,
  draft.html,
  draft.attachments.map((file) => [file.name, file.size, file.lastModified]),
]);

const formatBytes = (value: number | null, locale: string): string => {
  if (value === null) return '';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value / 1024)} KB`;
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value / (1024 * 1024))} MB`;
};

const deliveryStatusIcon = (status: EmailDeliveryStatus) => {
  if (status === 'delivered') return CheckCheck;
  if (status === 'delayed') return Clock3;
  if (status === 'bounced' || status === 'complained') return TriangleAlert;
  return Check;
};

function EmailComposeModal({
  onClose,
  onSent,
}: {
  onClose: () => void;
  onSent: (thread: EmailThreadDetail) => void;
}) {
  const { t } = useTranslation();
  const [to, setTo] = useState('');
  const [participantName, setParticipantName] = useState('');
  const [subject, setSubject] = useState('');
  const [draft, setDraft] = useState<EmailComposerValue>(emptyEmailComposerValue);
  const [profile, setProfile] = useState<EmailSenderProfile>('support');
  const idempotencyState = useRef<IdempotencyState>({
    fingerprint: '',
    key: crypto.randomUUID(),
  });

  const createMutation = useMutation({
    mutationFn: () => {
      const recipient = to.trim();
      const name = participantName.trim();
      const normalizedSubject = subject.trim();
      const fingerprint = emailDraftFingerprint(
        [recipient, name, normalizedSubject, profile],
        draft,
      );
      return adminCommunicationsAPI.createEmailThread({
        to: recipient,
        participant_name: name || undefined,
        subject: normalizedSubject,
        body: draft.text,
        html_body: draft.html || undefined,
        sender_profile: profile,
        idempotency_key: `email.create.${idempotencyKeyFor(idempotencyState, fingerprint)}`,
        attachments: draft.attachments,
      });
    },
    onSuccess: (thread) => {
      toast.success(t('adminCommunications.compose.sent'));
      onSent(thread);
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, error.response?.data?.detail, t('adminCommunications.compose.error')));
    },
  });

  const canSend = Boolean(to.trim() && subject.trim() && draft.text) && !createMutation.isPending;

  return (
    <ModalOverlay onClose={onClose} closeOnOverlayClick={!createMutation.isPending} className="!bg-black/70">
      <form
        className="w-full max-w-2xl overflow-hidden rounded-2xl border border-cyan-300/15 bg-[#111124] shadow-2xl shadow-black/50"
        onSubmit={(event) => {
          event.preventDefault();
          if (canSend) createMutation.mutate();
        }}
      >
        <header className="flex items-start gap-3 border-b border-white/10 bg-gradient-to-r from-cyan-400/10 to-transparent px-5 py-5 md:px-6">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-cyan-300/20 bg-cyan-400/10 text-cyan-300">
            <MailPlus className="h-5 w-5" />
          </span>
          <div>
            <h3 className="text-lg font-semibold text-white">{t('adminCommunications.compose.title')}</h3>
            <p className="mt-1 text-xs leading-5 text-gray-400">{t('adminCommunications.compose.description')}</p>
          </div>
        </header>

        <div className="space-y-4 px-5 py-5 md:px-6">
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
            <label className="block text-xs font-medium text-gray-300">
              {t('adminCommunications.compose.to')}
              <input
                type="email"
                required
                maxLength={255}
                value={to}
                onChange={(event) => setTo(event.target.value)}
                placeholder="name@company.com"
                className="mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-white placeholder:text-gray-600 focus:border-cyan-400/40 focus:outline-none focus:ring-2 focus:ring-cyan-400/20"
              />
            </label>
            <label className="block text-xs font-medium text-gray-300">
              {t('adminCommunications.compose.from')}
              <select
                value={profile}
                onChange={(event) => setProfile(event.target.value as EmailSenderProfile)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-[#19172d] px-3.5 py-2.5 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-cyan-400/40"
              >
                <option value="support">support@filamenthub.ru</option>
                <option value="partnerships">partners@filamenthub.ru</option>
                <option value="pr">pr@filamenthub.ru</option>
              </select>
            </label>
          </div>

          <label className="block text-xs font-medium text-gray-300">
            {t('adminCommunications.compose.name')}
            <input
              type="text"
              maxLength={200}
              value={participantName}
              onChange={(event) => setParticipantName(event.target.value)}
              placeholder={t('adminCommunications.compose.namePlaceholder')}
              className="mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-white placeholder:text-gray-600 focus:border-cyan-400/40 focus:outline-none focus:ring-2 focus:ring-cyan-400/20"
            />
          </label>

          <label className="block text-xs font-medium text-gray-300">
            {t('adminCommunications.compose.subject')}
            <input
              type="text"
              required
              maxLength={500}
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              className="mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-white focus:border-cyan-400/40 focus:outline-none focus:ring-2 focus:ring-cyan-400/20"
            />
          </label>

          <div className="block text-xs font-medium text-gray-300">
            {t('adminCommunications.compose.message')}
            <div className="mt-2">
              <EmailComposer
                id="admin-email-compose"
                disabled={createMutation.isPending}
                onChange={setDraft}
              />
            </div>
            <p className="mt-1.5 text-[11px] text-gray-500">
              {t('adminCommunications.compose.messagePlaceholder')}
            </p>
          </div>
        </div>

        <footer className="flex flex-col-reverse gap-3 border-t border-white/10 bg-black/10 px-5 py-4 sm:flex-row sm:items-center sm:justify-between md:px-6">
          <p className="text-[11px] leading-4 text-gray-500">{t('adminCommunications.richTextHint')}</p>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={createMutation.isPending}
              className="rounded-xl border border-white/10 px-4 py-2 text-sm text-gray-300 transition hover:bg-white/10 hover:text-white disabled:opacity-40"
            >
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              disabled={!canSend}
              className="inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send className="h-4 w-4" />
              {createMutation.isPending ? t('adminCommunications.sending') : t('adminCommunications.compose.send')}
            </button>
          </div>
        </footer>
      </form>
    </ModalOverlay>
  );
}

function AdminEmailInbox() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedThreadId, setSelectedThreadId] = useState<number | null>(null);
  const [filter, setFilter] = useState<ThreadFilter>('all');
  const [replyDraft, setReplyDraft] = useState<EmailComposerValue>(emptyEmailComposerValue);
  const [replyResetKey, setReplyResetKey] = useState(0);
  const [senderProfile, setSenderProfile] = useState<EmailSenderProfile>('support');
  const [composeOpen, setComposeOpen] = useState(false);
  const [deleteThreadId, setDeleteThreadId] = useState<number | null>(null);
  const replyIdempotencyState = useRef<IdempotencyState>({
    fingerprint: '',
    key: crypto.randomUUID(),
  });

  const listQuery = useQuery({
    queryKey: ['admin-email-threads', filter],
    queryFn: () => adminCommunicationsAPI.listEmailThreads({
      page: 1,
      size: 50,
      status: filter === 'all' ? undefined : filter,
    }),
  });

  const detailQuery = useQuery({
    queryKey: ['admin-email-thread', selectedThreadId],
    queryFn: () => adminCommunicationsAPI.getEmailThread(selectedThreadId as number),
    enabled: selectedThreadId !== null,
  });

  const updateCachedThread = (thread: EmailThreadDetail) => {
    queryClient.setQueryData(['admin-email-thread', thread.id], thread);
    queryClient.invalidateQueries({ queryKey: ['admin-email-threads'] });
  };

  const markReadMutation = useMutation({
    mutationFn: (threadId: number) => adminCommunicationsAPI.markEmailThreadRead(threadId),
    onSuccess: updateCachedThread,
  });

  const statusMutation = useMutation({
    mutationFn: ({ threadId, status }: { threadId: number; status: EmailThreadStatus }) =>
      adminCommunicationsAPI.updateEmailThread(threadId, status),
    onSuccess: updateCachedThread,
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, error.response?.data?.detail, t('adminCommunications.statusError')));
    },
  });

  const replyMutation = useMutation({
    mutationFn: ({
      threadId,
      draft,
      profile,
    }: {
      threadId: number;
      draft: EmailComposerValue;
      profile: EmailSenderProfile;
    }) => {
      const fingerprint = emailDraftFingerprint([threadId, profile], draft);
      return adminCommunicationsAPI.replyToEmailThread(threadId, {
        body: draft.text,
        html_body: draft.html || undefined,
        sender_profile: profile,
        idempotency_key: `email.reply.${idempotencyKeyFor(replyIdempotencyState, fingerprint)}`,
        attachments: draft.attachments,
      });
    },
    onSuccess: (_message: EmailMessage, variables) => {
      setReplyDraft(emptyEmailComposerValue());
      setReplyResetKey((value) => value + 1);
      replyIdempotencyState.current = {
        fingerprint: '',
        key: crypto.randomUUID(),
      };
      queryClient.invalidateQueries({ queryKey: ['admin-email-thread', variables.threadId] });
      queryClient.invalidateQueries({ queryKey: ['admin-email-threads'] });
      toast.success(t('adminCommunications.replySent'));
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, error.response?.data?.detail, t('adminCommunications.replyError')));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (threadId: number) => adminCommunicationsAPI.deleteEmailThread(threadId),
    onSuccess: () => {
      setDeleteThreadId(null);
      setSelectedThreadId(null);
      queryClient.invalidateQueries({ queryKey: ['admin-email-threads'] });
      toast.success(t('adminCommunications.delete.success'));
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, error.response?.data?.detail, t('adminCommunications.delete.error')));
    },
  });

  const downloadAttachmentMutation = useMutation({
    mutationFn: ({
      threadId,
      messageId,
      attachmentIndex,
    }: {
      threadId: number;
      messageId: number;
      attachmentIndex: number;
      filename: string;
    }) => adminCommunicationsAPI.downloadEmailAttachment(
      threadId,
      messageId,
      attachmentIndex,
    ),
    onSuccess: (blob, variables) => {
      downloadBlob(blob, variables.filename);
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(
        translateApiError(
          t,
          error.response?.data?.detail,
          t('adminCommunications.attachments.downloadError'),
        ),
      );
    },
  });

  useEffect(() => {
    const thread = detailQuery.data;
    if (thread && thread.unread_count > 0 && !markReadMutation.isPending) {
      markReadMutation.mutate(thread.id);
    }
  }, [detailQuery.data?.id, detailQuery.data?.unread_count]);

  useEffect(() => {
    const thread = detailQuery.data;
    if (thread) {
      setSenderProfile(thread.suggested_sender_profile);
      setReplyDraft(emptyEmailComposerValue());
      setReplyResetKey((value) => value + 1);
      replyIdempotencyState.current = {
        fingerprint: '',
        key: crypto.randomUUID(),
      };
    }
  }, [detailQuery.data?.id]);

  const dateFormatter = useMemo(
    () => new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium', timeStyle: 'short' }),
    [i18n.language],
  );
  const threads = listQuery.data?.items ?? [];
  const selectedThread = detailQuery.data;

  return (
    <>
      <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#121226]/70">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3 md:px-5">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl border border-cyan-400/20 bg-cyan-400/10 text-cyan-300">
            <Inbox className="h-5 w-5" />
          </span>
          <div>
            <h3 className="font-semibold text-white">{t('adminCommunications.inboxTitle')}</h3>
            <p className="text-xs text-gray-400">
              {t('adminCommunications.threadCount', { count: listQuery.data?.total ?? 0 })}
              {(listQuery.data?.unread_total ?? 0) > 0 && (
                <span className="ml-2 text-cyan-300">
                  {t('adminCommunications.unreadCount', { count: listQuery.data?.unread_total })}
                </span>
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setComposeOpen(true)}
            className="inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-3 py-2 text-xs font-semibold text-slate-950 transition hover:bg-cyan-300"
          >
            <MailPlus className="h-4 w-4" />
            <span className="hidden sm:inline">{t('adminCommunications.compose.action')}</span>
          </button>
          <div className="flex rounded-xl border border-white/10 bg-white/5 p-1">
            {(['all', 'open', 'closed'] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setFilter(value)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  filter === value ? 'bg-white/15 text-white shadow-sm' : 'text-gray-400 hover:text-white'
                }`}
              >
                {t(`adminCommunications.filters.${value}`)}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => listQuery.refetch()}
            className="rounded-xl border border-white/10 bg-white/5 p-2 text-gray-400 transition hover:bg-white/10 hover:text-white"
            title={t('adminCommunications.refresh')}
          >
            <RefreshCw className={`h-4 w-4 ${listQuery.isFetching ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="grid min-h-[600px] lg:grid-cols-[minmax(280px,0.88fr)_minmax(0,1.7fr)]">
        <aside className={`${selectedThreadId ? 'hidden lg:block' : 'block'} border-r border-white/10`}>
          {listQuery.isLoading ? (
            <div className="grid min-h-64 place-items-center text-sm text-gray-400">
              {t('adminCommunications.loading')}
            </div>
          ) : listQuery.isError ? (
            <div className="grid min-h-64 place-items-center px-6 text-center text-sm text-red-300">
              {t('adminCommunications.loadError')}
            </div>
          ) : threads.length === 0 ? (
            <div className="grid min-h-64 place-items-center px-6 text-center">
              <div>
                <Mail className="mx-auto mb-3 h-9 w-9 text-gray-600" />
                <p className="font-medium text-gray-300">{t('adminCommunications.emptyTitle')}</p>
                <p className="mt-1 text-xs leading-5 text-gray-500">{t('adminCommunications.emptyHint')}</p>
                <button
                  type="button"
                  onClick={() => setComposeOpen(true)}
                  className="mt-4 inline-flex items-center gap-2 rounded-xl border border-cyan-400/20 bg-cyan-400/10 px-3 py-2 text-xs font-medium text-cyan-300 hover:bg-cyan-400/15"
                >
                  <MailPlus className="h-4 w-4" />
                  {t('adminCommunications.compose.action')}
                </button>
              </div>
            </div>
          ) : (
            <div className="max-h-[720px] overflow-y-auto custom-scrollbar">
              {threads.map((thread) => (
                <button
                  key={thread.id}
                  type="button"
                  onClick={() => setSelectedThreadId(thread.id)}
                  className={`w-full border-b border-white/5 px-4 py-4 text-left transition ${
                    selectedThreadId === thread.id ? 'bg-cyan-400/10' : 'hover:bg-white/5'
                  }`}
                >
                  <div className="mb-1.5 flex items-start justify-between gap-3">
                    <span className={`truncate text-sm ${thread.unread_count ? 'font-semibold text-white' : 'font-medium text-gray-200'}`}>
                      {thread.participant_name || thread.participant_email}
                    </span>
                    {thread.unread_count > 0 && (
                      <span className="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-cyan-400 px-1.5 text-[10px] font-bold text-slate-950">
                        {thread.unread_count}
                      </span>
                    )}
                  </div>
                  <p className="truncate text-xs font-medium text-gray-300">{thread.subject}</p>
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-gray-500">{thread.latest_preview}</p>
                  <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-gray-500">
                    <span className="truncate">{thread.brand_name || thread.participant_email}</span>
                    <span className="shrink-0">{dateFormatter.format(new Date(thread.last_message_at))}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </aside>

        <section className={`${selectedThreadId ? 'block' : 'hidden lg:block'} min-w-0`}>
          {!selectedThreadId ? (
            <div className="grid min-h-[600px] place-items-center text-center">
              <div>
                <MessageCircle className="mx-auto mb-3 h-10 w-10 text-gray-600" />
                <p className="font-medium text-gray-300">{t('adminCommunications.selectThread')}</p>
              </div>
            </div>
          ) : detailQuery.isLoading || !selectedThread ? (
            <div className="grid min-h-[600px] place-items-center text-sm text-gray-400">
              {t('adminCommunications.loadingThread')}
            </div>
          ) : (
            <div className="flex min-h-[600px] flex-col">
              <header className="border-b border-white/10 px-4 py-4 md:px-6">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <button
                      type="button"
                      onClick={() => setSelectedThreadId(null)}
                      className="mt-0.5 rounded-lg p-1.5 text-gray-400 hover:bg-white/10 hover:text-white lg:hidden"
                    >
                      <ArrowLeft className="h-4 w-4" />
                    </button>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="truncate text-lg font-semibold text-white">{selectedThread.subject}</h4>
                        {selectedThread.brand_name && (
                          <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2 py-0.5 text-[11px] text-emerald-300">
                            <Building2 className="h-3 w-3" />
                            {selectedThread.brand_name}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 truncate text-xs text-gray-400">
                        {selectedThread.participant_name && `${selectedThread.participant_name} · `}
                        {selectedThread.participant_email}
                      </p>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      type="button"
                      onClick={() => statusMutation.mutate({
                        threadId: selectedThread.id,
                        status: selectedThread.status === 'open' ? 'closed' : 'open',
                      })}
                      disabled={statusMutation.isPending}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-gray-300 transition hover:bg-white/10 hover:text-white disabled:opacity-50"
                    >
                      {selectedThread.status === 'open' ? <Archive className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
                      <span className="hidden sm:inline">
                        {selectedThread.status === 'open' ? t('adminCommunications.closeThread') : t('adminCommunications.reopenThread')}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleteThreadId(selectedThread.id)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-xs text-rose-300 transition hover:bg-rose-400/20 hover:text-rose-200"
                      title={t('adminCommunications.delete.action')}
                    >
                      <Trash2 className="h-4 w-4" />
                      <span className="hidden sm:inline">{t('adminCommunications.delete.action')}</span>
                    </button>
                  </div>
                </div>
              </header>

              <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5 custom-scrollbar md:px-6">
                {selectedThread.messages.map((message) => {
                  const inbound = message.direction === 'inbound';
                  const DeliveryIcon = message.delivery_status ? deliveryStatusIcon(message.delivery_status) : null;
                  return (
                    <article
                      key={message.id}
                      className={`max-w-[90%] rounded-2xl border px-4 py-3 md:max-w-[82%] ${
                        inbound
                          ? 'mr-auto border-white/10 bg-white/[0.06] text-gray-200'
                          : 'ml-auto border-cyan-400/20 bg-cyan-400/10 text-cyan-50'
                      }`}
                    >
                      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-[11px]">
                        <span className={inbound ? 'text-gray-400' : 'text-cyan-300'}>
                          {message.sender_email}
                        </span>
                        <span className="flex items-center gap-2 text-gray-500">
                          {!inbound && message.delivery_status && DeliveryIcon && (
                            <span className={`inline-flex items-center gap-1 ${
                              message.delivery_status === 'bounced' || message.delivery_status === 'complained'
                                ? 'text-rose-300'
                                : message.delivery_status === 'delayed'
                                  ? 'text-amber-300'
                                  : 'text-cyan-300'
                            }`}>
                              <DeliveryIcon className="h-3.5 w-3.5" />
                              {t(`adminCommunications.delivery.${message.delivery_status}`)}
                            </span>
                          )}
                          <time>{dateFormatter.format(new Date(message.created_at))}</time>
                        </span>
                      </div>
                      {!inbound && message.html_body ? (
                        <div
                          className="break-words text-sm leading-6 [&_blockquote]:my-2 [&_blockquote]:border-l-2 [&_blockquote]:border-cyan-300/40 [&_blockquote]:pl-3 [&_h2]:my-2 [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:my-2 [&_h3]:font-semibold [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-1.5 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-black/20 [&_pre]:p-2 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5"
                          dangerouslySetInnerHTML={{ __html: message.html_body }}
                        />
                      ) : (
                        <p className="whitespace-pre-wrap break-words text-sm leading-6">
                          {message.text_body || t('adminCommunications.noTextBody')}
                        </p>
                      )}
                      {message.attachment_metadata.length > 0 && (
                        <div className="mt-3 space-y-1.5 border-t border-white/10 pt-3">
                          {message.attachment_metadata.map((attachment, index) => (
                            <button
                              key={`${attachment.filename}-${index}`}
                              type="button"
                              disabled={
                                !attachment.downloadable
                                || downloadAttachmentMutation.isPending
                              }
                              onClick={() => downloadAttachmentMutation.mutate({
                                threadId: selectedThread.id,
                                messageId: message.id,
                                attachmentIndex: attachment.index,
                                filename: attachment.filename,
                              })}
                              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-gray-400 transition enabled:hover:bg-white/10 enabled:hover:text-white disabled:cursor-default"
                            >
                              {attachment.downloadable ? (
                                <Download className="h-3.5 w-3.5 shrink-0 text-cyan-300" />
                              ) : (
                                <Paperclip className="h-3.5 w-3.5 shrink-0" />
                              )}
                              <span className="truncate">{attachment.filename}</span>
                              {attachment.size !== null && <span className="shrink-0 text-gray-500">{formatBytes(attachment.size, i18n.language)}</span>}
                            </button>
                          ))}
                          {message.attachment_metadata.every((attachment) => !attachment.downloadable) && (
                            <p className="text-[10px] leading-4 text-gray-500">
                              {t('adminCommunications.attachments.notAvailable')}
                            </p>
                          )}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>

              <form
                className="border-t border-white/10 bg-black/10 p-4 md:p-5"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (replyDraft.text) {
                    replyMutation.mutate({
                      threadId: selectedThread.id,
                      draft: replyDraft,
                      profile: senderProfile,
                    });
                  }
                }}
              >
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <label htmlFor="admin-email-reply" className="inline-flex items-center gap-2 text-xs font-medium text-gray-300">
                    <Reply className="h-3.5 w-3.5 text-cyan-300" />
                    {t('adminCommunications.replyLabel')}
                  </label>
                  <select
                    value={senderProfile}
                    onChange={(event) => setSenderProfile(event.target.value as EmailSenderProfile)}
                    className="rounded-lg border border-white/10 bg-[#19172d] px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-2 focus:ring-cyan-400/40"
                  >
                    <option value="support">support@filamenthub.ru</option>
                    <option value="partnerships">partners@filamenthub.ru</option>
                    <option value="pr">pr@filamenthub.ru</option>
                  </select>
                </div>
                <EmailComposer
                  id="admin-email-reply"
                  disabled={replyMutation.isPending}
                  resetKey={replyResetKey}
                  onChange={setReplyDraft}
                />
                <div className="mt-3 flex items-center justify-between gap-3">
                  <p className="text-[11px] text-gray-500">{t('adminCommunications.richTextHint')}</p>
                  <button
                    type="submit"
                    disabled={!replyDraft.text || replyMutation.isPending}
                    className="inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <Send className="h-4 w-4" />
                    {replyMutation.isPending ? t('adminCommunications.sending') : t('adminCommunications.sendReply')}
                  </button>
                </div>
              </form>
            </div>
          )}
        </section>
        </div>
      </div>
      {composeOpen && (
        <EmailComposeModal
          onClose={() => setComposeOpen(false)}
          onSent={(thread) => {
            setComposeOpen(false);
            setFilter('all');
            setSelectedThreadId(thread.id);
            queryClient.setQueryData(['admin-email-thread', thread.id], thread);
            queryClient.invalidateQueries({ queryKey: ['admin-email-threads'] });
          }}
        />
      )}
      <ConfirmModal
        isOpen={deleteThreadId !== null}
        onClose={() => {
          if (!deleteMutation.isPending) setDeleteThreadId(null);
        }}
        onConfirm={() => {
          if (deleteThreadId !== null) deleteMutation.mutate(deleteThreadId);
        }}
        title={t('adminCommunications.delete.title')}
        message={t('adminCommunications.delete.message')}
        confirmText={t('adminCommunications.delete.confirm')}
        isLoading={deleteMutation.isPending}
        variant="danger"
        icon={<Trash2 className="h-5 w-5" />}
      />
    </>
  );
}

export function AdminCommunications() {
  const { t } = useTranslation();
  const [section, setSection] = useState<CommunicationSection>('inbox');

  const sections = [
    { id: 'inbox' as const, icon: Inbox, label: t('adminCommunications.sections.inbox') },
    { id: 'feedback' as const, icon: MessageCircle, label: t('adminCommunications.sections.feedback') },
    { id: 'broadcasts' as const, icon: Send, label: t('adminCommunications.sections.broadcasts') },
  ];

  return (
    <div className="space-y-5">
      <header className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
            <Mail className="h-4 w-4" />
            {t('adminCommunications.eyebrow')}
          </div>
          <h2 className="text-2xl font-bold text-white">{t('adminCommunications.title')}</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-gray-400">{t('adminCommunications.description')}</p>
        </div>
        <nav className="flex w-full gap-1 rounded-xl border border-white/10 bg-black/15 p-1 md:w-auto" aria-label={t('adminCommunications.title')}>
          {sections.map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setSection(id)}
              className={`flex min-w-0 flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition md:flex-none ${
                section === id ? 'bg-cyan-400 text-slate-950 shadow-lg shadow-cyan-950/20' : 'text-gray-300 hover:bg-white/10 hover:text-white'
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="truncate">{label}</span>
            </button>
          ))}
        </nav>
      </header>

      {section === 'inbox' && <AdminEmailInbox />}
      {section === 'feedback' && <AdminFeedback />}
        {section === 'broadcasts' && <AdminNotificationCampaigns />}
    </div>
  );
}
