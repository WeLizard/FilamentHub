import { useMemo, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { AxiosError } from 'axios';
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  History,
  Link as LinkIcon,
  Search,
  Send,
  ShieldCheck,
  UserCheck,
  Users,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { adminAPI, adminNotificationsAPI } from '../../api/client';
import type {
  NotificationCampaignAudience,
  NotificationCampaignPreview,
  NotificationCampaignStatus,
} from '../../types/api';
import { translateApiError } from '../../utils/translateApiError';
import { ModalOverlay } from '../ModalOverlay';
import { toast } from '../Toast';
import { useDebounce } from '../../hooks/useDebounce';

const AUDIENCES: NotificationCampaignAudience[] = ['active', 'all', 'selected'];

const statusClass: Record<NotificationCampaignStatus, string> = {
  draft: 'border-amber-400/20 bg-amber-400/10 text-amber-300',
  sent: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300',
  cancelled: 'border-gray-400/20 bg-gray-400/10 text-gray-400',
  expired: 'border-rose-400/20 bg-rose-400/10 text-rose-300',
};

export function AdminNotificationCampaigns() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [audience, setAudience] = useState<NotificationCampaignAudience>('active');
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [link, setLink] = useState('');
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([]);
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search.trim(), 250);
  const [preview, setPreview] = useState<NotificationCampaignPreview | null>(null);

  const usersQuery = useQuery({
    queryKey: ['admin-users-for-campaign', debouncedSearch],
    queryFn: () => adminAPI.listUsers({
      page: 1,
      size: 100,
      active_only: true,
      search: debouncedSearch || undefined,
    }),
    enabled: audience === 'selected',
  });

  const historyQuery = useQuery({
    queryKey: ['admin-notification-campaigns'],
    queryFn: () => adminNotificationsAPI.history({ page: 1, size: 20 }),
  });

  const previewMutation = useMutation({
    mutationFn: () => adminNotificationsAPI.preview({
      audience,
      user_ids: audience === 'selected' ? selectedUserIds : undefined,
      title: title.trim(),
      message: message.trim(),
      link: link.trim() || null,
    }),
    onSuccess: (result) => {
      setPreview(result);
      queryClient.invalidateQueries({ queryKey: ['admin-notification-campaigns'] });
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(
        translateApiError(
          t,
          error.response?.data?.detail,
          t('adminNotifications.previewError'),
        ),
      );
    },
  });

  const confirmMutation = useMutation({
    mutationFn: (confirmationToken: string) =>
      adminNotificationsAPI.confirm(confirmationToken),
    onSuccess: (result) => {
      toast.success(
        t('adminNotifications.sentSuccess', { count: result.recipient_count }),
        5000,
      );
      setPreview(null);
      setTitle('');
      setMessage('');
      setLink('');
      setSelectedUserIds([]);
      setSearch('');
      queryClient.invalidateQueries({ queryKey: ['admin-notification-campaigns'] });
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(
        translateApiError(
          t,
          error.response?.data?.detail,
          t('adminNotifications.sendError'),
        ),
      );
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (campaignId: string) => adminNotificationsAPI.cancel(campaignId),
    onSuccess: () => {
      setPreview(null);
      queryClient.invalidateQueries({ queryKey: ['admin-notification-campaigns'] });
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(
        translateApiError(
          t,
          error.response?.data?.detail,
          t('adminNotifications.cancelError'),
        ),
      );
    },
  });

  const dateFormatter = useMemo(
    () => new Intl.DateTimeFormat(i18n.language, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }),
    [i18n.language],
  );

  const users = usersQuery.data?.items ?? [];
  const linkIsValid = !link.trim()
    || (
      link.trim().startsWith('/')
      && !link.trim().startsWith('//')
      && !link.includes('\\')
    );
  const canPreview = Boolean(
    title.trim()
    && message.trim()
    && linkIsValid
    && (audience !== 'selected' || selectedUserIds.length > 0),
  ) && !previewMutation.isPending;

  const toggleUser = (userId: number) => {
    setSelectedUserIds((current) => (
      current.includes(userId)
        ? current.filter((id) => id !== userId)
        : [...current, userId]
    ));
  };

  const closePreview = () => {
    if (preview && !confirmMutation.isPending && !cancelMutation.isPending) {
      cancelMutation.mutate(preview.campaign_id);
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (canPreview) previewMutation.mutate();
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
        <form
          onSubmit={handleSubmit}
          className="overflow-hidden rounded-2xl border border-white/10 bg-[#121226]/70"
        >
          <header className="border-b border-white/10 px-5 py-5">
            <div className="flex items-start gap-3">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-cyan-400/20 bg-cyan-400/10 text-cyan-300">
                <Send className="h-5 w-5" />
              </span>
              <div>
                <h2 className="font-semibold text-white">{t('adminNotifications.title')}</h2>
                <p className="mt-1 text-xs leading-5 text-gray-400">
                  {t('adminNotifications.subtitle')}
                </p>
              </div>
            </div>
          </header>

          <div className="space-y-5 p-5">
            <fieldset>
              <legend className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">
                {t('adminNotifications.audience')}
              </legend>
              <div className="grid gap-2 sm:grid-cols-3">
                {AUDIENCES.map((value) => {
                  const Icon = value === 'selected' ? UserCheck : Users;
                  return (
                    <button
                      key={value}
                      type="button"
                      onClick={() => {
                        setAudience(value);
                        if (value !== 'selected') setSelectedUserIds([]);
                      }}
                      className={`flex items-center gap-2 rounded-xl border px-3 py-2.5 text-left text-xs transition ${
                        audience === value
                          ? 'border-cyan-300/30 bg-cyan-400/10 text-cyan-200'
                          : 'border-white/10 bg-white/[0.03] text-gray-400 hover:bg-white/[0.06] hover:text-white'
                      }`}
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      {t(`adminNotifications.audiences.${value}`)}
                    </button>
                  );
                })}
              </div>
              {audience === 'all' && (
                <p className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-amber-300">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  {t('adminNotifications.includingInactive')}
                </p>
              )}
            </fieldset>

            {audience === 'selected' && (
              <div className="space-y-2">
                <label htmlFor="campaign-user-search" className="text-xs font-medium text-gray-300">
                  {t('adminNotifications.selectUsers', { count: selectedUserIds.length })}
                </label>
                <div className="relative">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-500" />
                  <input
                    id="campaign-user-search"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder={t('adminNotifications.searchUsersPlaceholder')}
                    className="w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-9 pr-3 text-sm text-white placeholder:text-gray-600 focus:border-cyan-400/30 focus:outline-none focus:ring-2 focus:ring-cyan-400/15"
                  />
                </div>
                <div className="max-h-64 overflow-y-auto rounded-xl border border-white/10 bg-black/10 p-2 custom-scrollbar">
                  {usersQuery.isLoading ? (
                    <p className="p-4 text-center text-xs text-gray-500">
                      {t('adminNotifications.loadingUsers')}
                    </p>
                  ) : users.length === 0 ? (
                    <p className="p-4 text-center text-xs text-gray-500">
                      {t('adminNotifications.noUsers')}
                    </p>
                  ) : (
                    users.map((user) => {
                      const selected = selectedUserIds.includes(user.id);
                      return (
                        <label
                          key={user.id}
                          className={`flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 transition ${
                            selected ? 'bg-cyan-400/10' : 'hover:bg-white/5'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={selected}
                            onChange={() => toggleUser(user.id)}
                            className="h-4 w-4 rounded border-white/20 bg-white/5 text-cyan-400 focus:ring-cyan-400"
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-xs font-medium text-gray-200">
                              {user.full_name || user.username}
                            </span>
                            <span className="block truncate text-[11px] text-gray-500">
                              {user.email} · @{user.username}
                            </span>
                          </span>
                        </label>
                      );
                    })
                  )}
                </div>
                {selectedUserIds.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {selectedUserIds.map((userId) => {
                      const user = users.find((item) => item.id === userId);
                      return (
                        <span
                          key={userId}
                          className="inline-flex items-center gap-1 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2 py-1 text-[11px] text-cyan-200"
                        >
                          {user?.username || `#${userId}`}
                          <button
                            type="button"
                            aria-label={t('adminNotifications.removeUser')}
                            onClick={() => toggleUser(userId)}
                            className="rounded-full p-0.5 hover:bg-white/10"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            <label className="block text-xs font-medium text-gray-300">
              {t('adminNotifications.titleLabel')}
              <input
                required
                maxLength={200}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder={t('adminNotifications.titlePlaceholder')}
                className="mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-white placeholder:text-gray-600 focus:border-cyan-400/30 focus:outline-none focus:ring-2 focus:ring-cyan-400/15"
              />
            </label>

            <label className="block text-xs font-medium text-gray-300">
              {t('adminNotifications.messageLabel')}
              <textarea
                required
                rows={7}
                maxLength={5000}
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                placeholder={t('adminNotifications.messagePlaceholder')}
                className="mt-2 w-full resize-y rounded-xl border border-white/10 bg-white/5 px-3.5 py-3 text-sm leading-6 text-white placeholder:text-gray-600 focus:border-cyan-400/30 focus:outline-none focus:ring-2 focus:ring-cyan-400/15"
              />
              <span className="mt-1 block text-right text-[10px] text-gray-600">
                {message.length}/5000
              </span>
            </label>

            <label className="block text-xs font-medium text-gray-300">
              <span className="inline-flex items-center gap-1.5">
                <LinkIcon className="h-3.5 w-3.5" />
                {t('adminNotifications.linkLabel')}
              </span>
              <input
                maxLength={500}
                value={link}
                onChange={(event) => setLink(event.target.value)}
                placeholder="/profile"
                className={`mt-2 w-full rounded-xl border bg-white/5 px-3.5 py-2.5 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:ring-2 ${
                  linkIsValid
                    ? 'border-white/10 focus:border-cyan-400/30 focus:ring-cyan-400/15'
                    : 'border-rose-400/40 focus:ring-rose-400/15'
                }`}
              />
              <span className={`mt-1 block text-[11px] ${linkIsValid ? 'text-gray-500' : 'text-rose-300'}`}>
                {linkIsValid
                  ? t('adminNotifications.linkHint')
                  : t('adminNotifications.linkInvalid')}
              </span>
            </label>
          </div>

          <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 bg-black/10 px-5 py-4">
            <p className="inline-flex items-center gap-1.5 text-[11px] text-gray-500">
              <ShieldCheck className="h-3.5 w-3.5 text-cyan-300" />
              {t('adminNotifications.previewRequired')}
            </p>
            <button
              type="submit"
              disabled={!canPreview}
              className="inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ShieldCheck className="h-4 w-4" />
              {previewMutation.isPending
                ? t('adminNotifications.previewing')
                : t('adminNotifications.preview')}
            </button>
          </footer>
        </form>

        <section className="overflow-hidden rounded-2xl border border-white/10 bg-[#121226]/70">
          <header className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-4">
            <div className="flex items-center gap-2">
              <History className="h-4 w-4 text-cyan-300" />
              <h3 className="text-sm font-semibold text-white">
                {t('adminNotifications.history.title')}
              </h3>
            </div>
            <span className="text-[11px] text-gray-500">
              {historyQuery.data?.total ?? 0}
            </span>
          </header>
          <div className="max-h-[720px] overflow-y-auto custom-scrollbar">
            {historyQuery.isLoading ? (
              <p className="p-6 text-center text-xs text-gray-500">
                {t('adminNotifications.history.loading')}
              </p>
            ) : !historyQuery.data?.items.length ? (
              <p className="p-6 text-center text-xs leading-5 text-gray-500">
                {t('adminNotifications.history.empty')}
              </p>
            ) : (
              historyQuery.data.items.map((campaign) => (
                <article
                  key={campaign.campaign_id}
                  className="border-b border-white/5 px-4 py-4 last:border-b-0"
                >
                  <div className="flex items-start justify-between gap-3">
                    <h4 className="line-clamp-2 text-xs font-medium leading-5 text-gray-200">
                      {campaign.title}
                    </h4>
                    <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] ${statusClass[campaign.status]}`}>
                      {t(`adminNotifications.history.status.${campaign.status}`)}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-gray-500">
                    {campaign.message}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[10px] text-gray-600">
                    <span>
                      {t('adminNotifications.history.recipients', {
                        count: campaign.recipient_count,
                      })}
                    </span>
                    <time>{dateFormatter.format(new Date(campaign.created_at))}</time>
                  </div>
                  <p className="mt-1 text-[10px] text-gray-600">
                    {campaign.created_by_name}
                  </p>
                </article>
              ))
            )}
          </div>
        </section>
      </div>

      {preview && (
        <ModalOverlay
          onClose={closePreview}
          closeOnOverlayClick={!confirmMutation.isPending && !cancelMutation.isPending}
          closeOnEscape={!confirmMutation.isPending && !cancelMutation.isPending}
          className="!bg-black/75"
        >
          <div className="w-full max-w-2xl overflow-hidden rounded-2xl border border-cyan-300/20 bg-[#101021] shadow-2xl shadow-black/60">
            <header className="flex items-start gap-3 border-b border-white/10 bg-cyan-400/[0.06] px-5 py-5">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-cyan-400/20 bg-cyan-400/10 text-cyan-300">
                <ShieldCheck className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <h3 className="font-semibold text-white">
                  {t('adminNotifications.previewTitle')}
                </h3>
                <p className="mt-1 text-xs leading-5 text-gray-400">
                  {t('adminNotifications.previewSubtitle', {
                    count: preview.recipient_count,
                  })}
                </p>
              </div>
            </header>

            <div className="max-h-[70vh] space-y-4 overflow-y-auto p-5 custom-scrollbar">
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                  <p className="text-[10px] uppercase tracking-wider text-gray-600">
                    {t('adminNotifications.audience')}
                  </p>
                  <p className="mt-1 text-sm font-medium text-gray-200">
                    {t(`adminNotifications.audiences.${preview.audience}`)}
                  </p>
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                  <p className="text-[10px] uppercase tracking-wider text-gray-600">
                    {t('adminNotifications.previewRecipients')}
                  </p>
                  <p className="mt-1 text-sm font-medium text-cyan-200">
                    {preview.recipient_count}
                  </p>
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                  <p className="text-[10px] uppercase tracking-wider text-gray-600">
                    {t('adminNotifications.previewExpires')}
                  </p>
                  <p className="mt-1 text-xs font-medium text-gray-300">
                    {dateFormatter.format(new Date(preview.confirmation_expires_at))}
                  </p>
                </div>
              </div>

              {preview.excluded_user_ids.length > 0 && (
                <div className="flex gap-2 rounded-xl border border-amber-400/20 bg-amber-400/10 p-3 text-xs leading-5 text-amber-200">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  {t('adminNotifications.previewExcluded', {
                    count: preview.excluded_user_ids.length,
                  })}
                </div>
              )}

              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <h4 className="text-sm font-semibold text-white">{preview.title}</h4>
                <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-gray-300">
                  {preview.message}
                </p>
                {preview.link && (
                  <p className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-cyan-400/10 px-2 py-1 text-[11px] text-cyan-300">
                    <LinkIcon className="h-3 w-3" />
                    {preview.link}
                  </p>
                )}
              </div>

              <div>
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-600">
                  {t('adminNotifications.previewSample')}
                </p>
                <div className="divide-y divide-white/5 overflow-hidden rounded-xl border border-white/10">
                  {preview.recipient_sample.map((recipient) => (
                    <div
                      key={recipient.id}
                      className="flex items-center justify-between gap-3 bg-white/[0.025] px-3 py-2.5"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-xs text-gray-200">
                          {recipient.full_name || recipient.username}
                        </span>
                        <span className="block truncate text-[10px] text-gray-500">
                          {recipient.email}
                        </span>
                      </span>
                      <span className="text-[10px] text-gray-600">#{recipient.id}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <footer className="flex flex-col-reverse gap-3 border-t border-white/10 bg-black/10 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="inline-flex items-center gap-1.5 text-[11px] text-gray-500">
                <Clock3 className="h-3.5 w-3.5" />
                {t('adminNotifications.previewImmutable')}
              </p>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  disabled={confirmMutation.isPending || cancelMutation.isPending}
                  onClick={closePreview}
                  className="rounded-xl border border-white/10 px-4 py-2 text-sm text-gray-300 hover:bg-white/10 disabled:opacity-40"
                >
                  {cancelMutation.isPending
                    ? t('adminNotifications.cancelling')
                    : t('adminNotifications.cancelPreview')}
                </button>
                <button
                  type="button"
                  disabled={confirmMutation.isPending || cancelMutation.isPending}
                  onClick={() => confirmMutation.mutate(preview.confirmation_token)}
                  className="inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300 disabled:opacity-40"
                >
                  <CheckCircle2 className="h-4 w-4" />
                  {confirmMutation.isPending
                    ? t('adminNotifications.sending')
                    : t('adminNotifications.confirmSend')}
                </button>
              </div>
            </footer>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}
