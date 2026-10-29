import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { MessageCircle, X } from 'lucide-react';
import type { Notification } from '../types/api';

export interface NotificationText {
  title: string;
  message: string;
}

type FeedEntry =
  | { kind: 'thread'; feedbackId: number; items: Notification[] }
  | { kind: 'single'; item: Notification };

export function feedbackIdOf(notification: Notification): number | null {
  if (notification.type !== 'admin_message') return null;
  const id = Number(notification.extra_data?.feedback_id);
  return Number.isInteger(id) && id > 0 ? id : null;
}

/** Support replies are grouped per conversation so one thread is one row. */
function buildFeed(notifications: Notification[]): { threads: FeedEntry[]; others: FeedEntry[] } {
  const threads = new Map<number, Notification[]>();
  const others: FeedEntry[] = [];
  for (const notification of notifications) {
    const feedbackId = feedbackIdOf(notification);
    if (feedbackId === null) {
      others.push({ kind: 'single', item: notification });
      continue;
    }
    const group = threads.get(feedbackId);
    if (group) group.push(notification);
    else threads.set(feedbackId, [notification]);
  }
  return {
    threads: Array.from(threads, ([feedbackId, items]) => ({ kind: 'thread' as const, feedbackId, items })),
    others,
  };
}

interface NotificationFeedListProps {
  notifications: Notification[];
  getText: (notification: Notification) => NotificationText;
  getIcon: (notification: Notification) => ReactNode;
  formatTime: (dateString: string) => string;
  onOpen: (notification: Notification) => void;
  onOpenThread: (feedbackId: number, items: Notification[]) => void;
  onDelete: (ids: number[]) => void;
  deletePending: boolean;
}

export function NotificationFeedList({
  notifications,
  getText,
  getIcon,
  formatTime,
  onOpen,
  onOpenThread,
  onDelete,
  deletePending,
}: NotificationFeedListProps) {
  const { t } = useTranslation();
  const { threads, others } = buildFeed(notifications);

  const row = (
    key: string,
    {
      icon,
      title,
      preview,
      time,
      unread,
      badge,
      onClick,
      deleteIds,
    }: {
      icon: ReactNode;
      title: string;
      preview: string;
      time: string;
      unread: boolean;
      badge?: string;
      onClick: () => void;
      deleteIds: number[] | null;
    },
  ) => (
    <div
      key={key}
      className={`group flex items-start transition-colors hover:bg-white/10 ${unread ? 'bg-white/[0.06]' : ''}`}
    >
      <button
        type="button"
        onClick={onClick}
        className="flex min-h-11 min-w-0 flex-1 cursor-pointer items-start gap-3 px-3 py-2.5 text-left focus-visible:bg-white/10 focus-visible:outline-none"
      >
        <span className="mt-0.5 flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-white/5">{icon}</span>
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-2">
            <span className={`min-w-0 flex-1 truncate text-sm ${unread ? 'font-semibold text-white' : 'font-medium text-gray-200'}`}>
              {title}
            </span>
            <span className="flex-none text-[11px] text-gray-400">{time}</span>
          </span>
          <span className="mt-0.5 line-clamp-2 break-words text-xs leading-5 text-gray-300/90">{preview}</span>
          {badge && (
            <span className="mt-1 inline-flex rounded-full bg-cyan-400/15 px-2 py-0.5 text-[11px] font-medium text-cyan-200">
              {badge}
            </span>
          )}
        </span>
        {unread && <span className="mt-2 h-2 w-2 flex-none rounded-full bg-cyan-400" aria-hidden="true" />}
      </button>
      {deleteIds && (
        <button
          type="button"
          onClick={() => onDelete(deleteIds)}
          disabled={deletePending}
          className="mr-1 mt-1 flex h-11 w-11 flex-none items-center justify-center rounded-lg text-gray-400 transition hover:bg-white/10 hover:text-red-400 md:opacity-0 md:focus-visible:opacity-100 md:group-hover:opacity-100"
          title={t('notifications.deleteOne')}
          aria-label={t('notifications.deleteOne')}
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );

  const threadRows = threads.map((entry) => {
    if (entry.kind !== 'thread') return null;
    const latest = entry.items[0];
    const unreadCount = entry.items.filter((item) => !item.read).length;
    const subject = typeof latest.extra_data?.feedback_subject === 'string'
      ? latest.extra_data.feedback_subject
      : '';
    return row(`thread-${entry.feedbackId}`, {
      icon: <MessageCircle className="h-4 w-4 text-cyan-300" />,
      title: subject
        ? `#${entry.feedbackId} · ${subject}`
        : t('notifications.feedbackThreadTitle', { id: entry.feedbackId }),
      preview: getText(latest).message,
      time: formatTime(latest.created_at),
      unread: unreadCount > 0,
      badge: unreadCount > 1 ? t('notifications.newReplies', { count: unreadCount }) : undefined,
      onClick: () => onOpenThread(entry.feedbackId, entry.items),
      deleteIds: entry.items.map((item) => item.id),
    });
  });

  const otherRows = others.map((entry) => {
    if (entry.kind !== 'single') return null;
    const { item } = entry;
    const { title, message } = getText(item);
    return row(`n-${item.id}`, {
      icon: getIcon(item),
      title,
      preview: message,
      time: formatTime(item.created_at),
      unread: !item.read,
      onClick: () => onOpen(item),
      deleteIds: item.type === 'preset_locally_deleted' ? null : [item.id],
    });
  });

  const sectionLabel = (label: string) => (
    <p className="px-3 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wide text-purple-200/70">{label}</p>
  );

  return (
    <div>
      {threadRows.length > 0 && (
        <section>
          {sectionLabel(t('notifications.sections.support'))}
          <div className="divide-y divide-white/5">{threadRows}</div>
        </section>
      )}
      {otherRows.length > 0 && (
        <section>
          {threadRows.length > 0 && sectionLabel(t('notifications.sections.other'))}
          <div className="divide-y divide-white/5">{otherRows}</div>
        </section>
      )}
    </div>
  );
}
