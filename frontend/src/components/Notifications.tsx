/** Компонент уведомлений с колокольчиком */

import React, { useState, useRef, useEffect, useId, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  ArrowRight,
  Bell,
  CheckCircle,
  Info,
  MessageCircle,
  PackageMinus,
  Settings,
  Trash2,
  X,
  XCircle,
} from 'lucide-react';
import { ModalOverlay } from './ModalOverlay';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { notificationsAPI } from '../api/client';
import type { Notification, NotificationType } from '../types/api';
import { DeletedPresetsModal } from './DeletedPresetsModal';
import { FeedbackThreadView } from './FeedbackThreadView';
import { NotificationFeedList } from './NotificationFeedList';

interface NotificationsProps {
  floating?: boolean; // Плавающая версия для OrcaSlicer (когда нет хедера)
}

interface NotificationPresentation {
  sourceKey: string;
  typeKey: string;
  actionKey: string;
}

const DIRECT_LINK_MAX_MESSAGE = 140;

const getNotificationPresentation = (
  notification: Notification,
): NotificationPresentation => {
  switch (notification.type) {
    case 'preset_updated':
      return {
        sourceKey: 'notifications.sources.service',
        typeKey: 'notifications.types.presetUpdated',
        actionKey: 'notifications.actions.openFilament',
      };
    case 'preset_deleted':
      return {
        sourceKey: 'notifications.sources.service',
        typeKey: 'notifications.types.presetDeleted',
        actionKey: 'notifications.actions.openFilament',
      };
    case 'preset_locally_deleted':
      return {
        sourceKey: 'notifications.sources.orca',
        typeKey: 'notifications.types.localPresets',
        actionKey: 'notifications.actions.open',
      };
    case 'brand_verified':
      return {
        sourceKey: 'notifications.sources.service',
        typeKey: 'notifications.types.brandVerified',
        actionKey: 'notifications.actions.openBrand',
      };
    case 'brand_request_approved':
      return {
        sourceKey: 'notifications.sources.service',
        typeKey: 'notifications.types.brandRequestApproved',
        actionKey: 'notifications.actions.openBrand',
      };
    case 'brand_request_rejected':
      return {
        sourceKey: 'notifications.sources.service',
        typeKey: 'notifications.types.brandRequestRejected',
        actionKey: 'notifications.actions.open',
      };
    case 'admin_message':
      return {
        sourceKey: 'notifications.sources.administration',
        typeKey: notification.extra_data?.feedback_id
          ? 'notifications.types.feedbackResponse'
          : 'notifications.types.adminMessage',
        actionKey: notification.extra_data?.feedback_id
          ? 'notifications.actions.openResponse'
          : 'notifications.actions.open',
      };
    case 'low_stock_spool':
    case 'low_stock_material':
      return {
        sourceKey: 'notifications.sources.service',
        typeKey: 'notifications.types.lowStock',
        actionKey: 'notifications.actions.openSpools',
      };
    default:
      return {
        sourceKey: 'notifications.sources.service',
        typeKey: 'notifications.types.notification',
        actionKey: 'notifications.actions.open',
      };
  }
};

export const Notifications: React.FC<NotificationsProps> = ({ floating = false }) => {
  const { t, i18n } = useTranslation();
  const { user, refreshUser } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const panelId = useId();
  const detailTitleId = useId();
  const dropdownRef = useRef<HTMLDivElement>(null);
  const lastAccountRefreshNotificationId = useRef<number | null>(null);
  const [selectedNotification, setSelectedNotification] = useState<Notification | null>(null);
  const [viewNotification, setViewNotification] = useState<Notification | null>(null);
  const [threadFeedbackId, setThreadFeedbackId] = useState<number | null>(null);
  const threadTitleId = useId();
  
  // Для плавающей версии используем внутренний счётчик (обновляется через postMessage от C++)
  const [externalUnreadCount, setExternalUnreadCount] = useState<number | null>(null);

  // Загружаем уведомления
  const {
    data: notificationsData,
    isError: isNotificationsError,
    isLoading: isNotificationsLoading,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isFetchNextPageError,
  } = useInfiniteQuery({
    queryKey: ['notifications', user?.id],
    queryFn: ({ pageParam, signal }) => notificationsAPI.listFeed({
      limit: 50,
      ...(pageParam !== null ? { cursor: pageParam } : {}),
    }, signal),
    initialPageParam: null as number | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!user,
    staleTime: 30_000,
    refetchInterval: 120_000,
    refetchOnWindowFocus: true,
  });

  const notifications = useMemo(
    () => notificationsData?.pages.flatMap((page) => page.items) || [],
    [notificationsData?.pages],
  );

  // Brand approval happens in another admin session. Keep the active account
  // context in sync as soon as the corresponding notification reaches the user.
  useEffect(() => {
    const accountChangeNotification = notifications
      .filter((notification) => (
        notification.type === 'brand_request_approved'
        || notification.type === 'brand_verified'
      ))
      .reduce<Notification | null>(
        (latest, notification) => (!latest || notification.id > latest.id ? notification : latest),
        null,
      );

    if (
      !accountChangeNotification
      || lastAccountRefreshNotificationId.current === accountChangeNotification.id
    ) {
      return;
    }

    lastAccountRefreshNotificationId.current = accountChangeNotification.id;
    void refreshUser();
  }, [notifications, refreshUser]);

  // Для плавающей версии используем внешний счётчик (от C++), иначе счётчик из API
  const unreadCount = floating && externalUnreadCount !== null 
    ? externalUnreadCount 
    : (notificationsData?.pages[0]?.unread_count || 0);

  // Мутация для отметки как прочитанное
  const markAsReadMutation = useMutation({
    mutationFn: (notificationId: number) => notificationsAPI.markAsRead(notificationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications', user?.id] });
    },
  });

  // Мутация для отметки всех как прочитанные
  const markAllAsReadMutation = useMutation({
    mutationFn: () => notificationsAPI.markAllAsRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications', user?.id] });
    },
  });

  // Мутация для удаления уведомления
  const deleteNotificationMutation = useMutation({
    mutationFn: (notificationId: number) => notificationsAPI.delete(notificationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications', user?.id] });
    },
  });

  const deleteNotificationsMutation = useMutation({
    mutationFn: (ids: number[]) => Promise.all(ids.map((id) => notificationsAPI.delete(id))),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications', user?.id] });
    },
  });

  const markNotificationsReadMutation = useMutation({
    mutationFn: (ids: number[]) => Promise.all(ids.map((id) => notificationsAPI.markAsRead(id))),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications', user?.id] });
    },
  });

  // Мутация для удаления всех уведомлений
  const deleteAllNotificationsMutation = useMutation({
    mutationFn: () => notificationsAPI.deleteAll(),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['notifications', user?.id] });
      if (result.skipped_pending_count === 0) {
        setIsOpen(false);
      }
    },
  });

  // Обработка сообщений от C++ кода (только для плавающей версии в OrcaSlicer)
  useEffect(() => {
    if (!floating) return;

    const handleMessage = (event: MessageEvent) => {
      // Принимаем только от нашего origin или от OrcaSlicer (file:// / null origin)
      if (event.origin !== window.location.origin && event.origin !== 'null' && event.origin !== 'file://') return;
      if (event.data && typeof event.data === 'object' && event.data.command === 'update_notifications_count') {
        const count = event.data.count || 0;
        setExternalUnreadCount(count);
        // Также обновляем данные через API для получения полного списка уведомлений
        refetch();
      }
    };

    window.addEventListener('message', handleMessage);
    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, [floating, refetch]);

  // Закрытие при клике вне компонента
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  if (!user) {
    return null;
  }

  const getNotificationIcon = (type: NotificationType) => {
    switch (type) {
      case 'preset_updated':
        return <Settings className="w-5 h-5 text-blue-400" />;
      case 'preset_deleted':
        return <XCircle className="w-5 h-5 text-red-400" />;
      case 'preset_locally_deleted':
        return <XCircle className="w-5 h-5 text-yellow-400" />;
      case 'brand_verified':
        return <CheckCircle className="w-5 h-5 text-green-400" />;
      case 'brand_request_approved':
        return <CheckCircle className="w-5 h-5 text-green-400" />;
      case 'brand_request_rejected':
        return <AlertCircle className="w-5 h-5 text-yellow-400" />;
      case 'admin_message':
        return <MessageCircle className="w-5 h-5 text-purple-400" />;
      case 'low_stock_spool':
      case 'low_stock_material':
        return <PackageMinus className="w-5 h-5 text-amber-400" />;
      default:
        return <Info className="w-5 h-5 text-blue-400" />;
    }
  };

  const handleNotificationClick = (notification: Notification) => {
    // Для уведомлений о локально удалённых пресетах открываем специальную модалку
    if (notification.type === 'preset_locally_deleted') {
      setSelectedNotification(notification);
      setIsOpen(false);
      return;
    }

    setIsOpen(false);

    // A short notice with a destination goes straight there; long texts and
    // messages without a link are read in the dialog first.
    const { message } = getNotificationText(notification);
    const link = notification.link;
    if (link && message.length <= DIRECT_LINK_MAX_MESSAGE) {
      // Leaving the site would cancel the read request, so external links wait for it.
      if (!notification.read && !link.trim().startsWith('/')) {
        void markAsReadMutation.mutateAsync(notification.id)
          .catch(() => undefined)
          .finally(() => handleOpenLink(link));
        return;
      }
      if (!notification.read) markAsReadMutation.mutate(notification.id);
      handleOpenLink(link);
      return;
    }
    if (!notification.read) markAsReadMutation.mutate(notification.id);
    setViewNotification(notification);
  };

  const openFeedbackThread = (feedbackId: number, items: Notification[]) => {
    const unreadIds = items.filter((item) => !item.read).map((item) => item.id);
    if (unreadIds.length) markNotificationsReadMutation.mutate(unreadIds);
    setIsOpen(false);
    setThreadFeedbackId(feedbackId);
  };

  const handleOpenLink = (link: string) => {
    const trimmedLink = link.trim();
    
    // Проверяем, является ли ссылка абсолютной (начинается с http:// или https://)
    const hasProtocol = /^https?:\/\//i.test(trimmedLink);
    
    // Проверяем, является ли ссылка относительным путём (начинается с /)
    const isRelativePath = trimmedLink.startsWith('/');
    
    if (hasProtocol) {
      // Для абсолютных URL с протоколом открываем напрямую
      window.location.href = trimmedLink;
    } else if (isRelativePath) {
      // Для относительных путей (начинаются с /) используем React Router
      navigate(trimmedLink);
      setViewNotification(null);
    } else {
      // Для ссылок без протокола (например, mr-lizard.ru/games)
      // добавляем https:// и открываем как внешний URL
      window.location.href = `https://${trimmedLink}`;
    }
  };

  const handleMarkAllAsRead = () => {
    markAllAsReadMutation.mutate();
  };

  const formatTime = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return t('notifications.justNow');
    if (diffMins < 60) return t('notifications.minsAgo', { count: diffMins });
    if (diffHours < 24) return t('notifications.hoursAgo', { count: diffHours });
    if (diffDays < 7) return t('notifications.daysAgo', { count: diffDays });
    return date.toLocaleDateString(i18n.resolvedLanguage || i18n.language);
  };

  const getNotificationText = (notification: Notification) => {
    const params = notification.extra_data || {};
    const titleKey = `notifications.keys.${notification.title}`;
    const messageKey = `notifications.keys.${notification.message}`;
    const translatedTitle = t(titleKey, params);
    const translatedMessage = t(messageKey, params);
    const normalizedTitle = typeof translatedTitle === 'string' ? translatedTitle : notification.title;
    const normalizedMessage = typeof translatedMessage === 'string' ? translatedMessage : notification.message;
    const title = normalizedTitle === titleKey ? notification.title : normalizedTitle;
    let message = normalizedMessage === messageKey ? notification.message : normalizedMessage;
    const unknownCount = Number(params.unknown_count);
    if (notification.type === 'low_stock_material' && unknownCount > 0) {
      message = `${message} ${t('notifications.keys.low_stock_material_unknown', { count: unknownCount })}`;
    }
    return { title, message };
  };

  const viewNotificationText = viewNotification ? getNotificationText(viewNotification) : null;
  const viewNotificationPresentation = viewNotification
    ? getNotificationPresentation(viewNotification)
    : null;

  const loadMoreControl = (hasNextPage || isFetchNextPageError) ? (
    <div className="border-t border-white/10 p-3 text-center">
      {hasNextPage && (
        <button
          type="button"
          onClick={() => void fetchNextPage()}
          disabled={isFetchingNextPage}
          className="inline-flex min-h-11 items-center justify-center rounded-lg px-4 py-2 text-sm font-medium text-purple-300 transition-colors hover:bg-white/10 hover:text-purple-200 disabled:cursor-wait disabled:opacity-60"
        >
          {isFetchingNextPage ? t('notifications.loadingMore') : t('notifications.loadMore')}
        </button>
      )}
      {isFetchNextPageError && (
        <p className="mt-1 text-xs text-rose-300" role="alert">
          {t('notifications.loadMoreError')}
        </p>
      )}
    </div>
  ) : null;

  const threadModal = threadFeedbackId !== null ? (
    <ModalOverlay onClose={() => setThreadFeedbackId(null)}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={threadTitleId}
        className="w-full max-w-3xl"
      >
        <FeedbackThreadView
          feedbackId={threadFeedbackId}
          titleId={threadTitleId}
          onClose={() => setThreadFeedbackId(null)}
        />
      </div>
    </ModalOverlay>
  ) : null;

  // Плавающая версия (для OrcaSlicer)
  if (floating) {
    return (
      <div 
        className="fixed bottom-6 right-6 z-[9999]"
        ref={dropdownRef}
      >
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="relative flex items-center justify-center w-14 h-14 rounded-full bg-gradient-to-br from-purple-600 to-indigo-600 text-white shadow-2xl hover:shadow-purple-500/50 transition-all hover:scale-110 active:scale-95"
          aria-label={unreadCount > 0
            ? `${t('notifications.title')}: ${t('notifications.newCount', { count: unreadCount })}`
            : t('notifications.title')}
          aria-expanded={isOpen}
          aria-controls={panelId}
        >
          <Bell className="w-6 h-6" />
          {unreadCount > 0 && (
            <span className="absolute -top-1 -right-1 w-6 h-6 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center ring-2 ring-purple-900">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>

        {isOpen && (
          <div
            id={panelId}
            role="region"
            aria-label={t('notifications.title')}
            className="absolute right-0 bottom-full mb-4 w-[26rem] max-w-[calc(100vw-24px)] bg-gradient-to-br from-purple-900 to-indigo-900 rounded-xl border border-white/20 shadow-2xl z-[10000] max-h-[80vh] overflow-hidden flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-white/10">
              <h3 className="text-lg font-bold text-white">{t('notifications.title')}</h3>
              {unreadCount > 0 && (
                <span className="px-2 py-1 bg-purple-600 text-white text-xs font-semibold rounded-full">
                  {t('notifications.newCount', { count: unreadCount })}
                </span>
              )}
            </div>

            {/* Notifications List - тот же код что ниже */}
            <div className="overflow-y-auto flex-1">
              {isNotificationsLoading && !notificationsData ? (
                <div className="p-8 text-center text-gray-400" role="status">
                  <div className="w-7 h-7 mx-auto mb-3 border-2 border-purple-300/30 border-t-purple-300 rounded-full animate-spin" />
                  <p>{t('notifications.loading')}</p>
                </div>
              ) : isNotificationsError && notifications.length === 0 ? (
                <div className="p-8 text-center text-gray-400" role="alert">
                  <AlertCircle className="w-10 h-10 mx-auto mb-3 text-yellow-400/80" />
                  <p className="mb-3">{t('notifications.loadError')}</p>
                  <button
                    type="button"
                    onClick={() => void refetch()}
                    className="text-sm font-medium text-purple-300 hover:text-purple-200 transition-colors"
                  >
                    {t('notifications.retry')}
                  </button>
                </div>
              ) : notifications.length === 0 ? (
                <div className="p-8 text-center text-gray-400">
                  <Bell className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>{t('notifications.empty')}</p>
                </div>
              ) : (
                <NotificationFeedList
                  notifications={notifications}
                  getText={getNotificationText}
                  getIcon={(notification) => getNotificationIcon(notification.type)}
                  formatTime={formatTime}
                  onOpen={handleNotificationClick}
                  onOpenThread={openFeedbackThread}
                  onDelete={(ids) => deleteNotificationsMutation.mutate(ids)}
                  deletePending={deleteNotificationsMutation.isPending}
                />
              )}
            </div>

            {loadMoreControl}

            {/* Footer - тот же код что ниже */}
            {notifications.length > 0 && (
              <div className="p-3 border-t border-white/10 space-y-2">
                {unreadCount > 0 && (
                  <button
                    className="min-h-11 w-full py-2 text-center text-sm text-purple-400 transition-all hover:text-purple-300"
                    onClick={() => {
                      handleMarkAllAsRead();
                    }}
                    disabled={markAllAsReadMutation.isPending}
                  >
                    {markAllAsReadMutation.isPending ? t('notifications.processing') : t('notifications.markAllRead')}
                  </button>
                )}
                <button
                  className="flex min-h-11 w-full items-center justify-center gap-2 py-2 text-center text-sm text-red-400 transition-all hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => {
                    deleteAllNotificationsMutation.mutate();
                  }}
                  disabled={deleteAllNotificationsMutation.isPending}
                >
                  {deleteAllNotificationsMutation.isPending ? (
                    <>
                      <div className="w-4 h-4 border-2 border-red-400/30 border-t-red-400 rounded-full animate-spin" />
                      {t('notifications.clearing')}
                    </>
                  ) : (
                    <>
                      <Trash2 className="w-4 h-4" />
                      {t('notifications.clearAll')}
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        )}
        
        {threadModal}

        {/* Modal for deleted presets */}
        {selectedNotification && (
          <DeletedPresetsModal
            isOpen={!!selectedNotification}
            onClose={() => {
              setSelectedNotification(null);
              queryClient.invalidateQueries({ queryKey: ['notifications', user?.id] });
            }}
            notification={selectedNotification}
          />
        )}

        {/* Modal for viewing notification */}
        {viewNotification && viewNotificationText && viewNotificationPresentation && (
          <ModalOverlay onClose={() => setViewNotification(null)}>
              <div
                role="dialog"
                aria-modal="true"
                aria-labelledby={detailTitleId}
                className="bg-gradient-to-br from-purple-900 to-indigo-900 rounded-2xl max-w-2xl w-full overflow-hidden flex flex-col border border-white/20 shadow-2xl max-h-[85vh]"
              >
                {/* Header */}
                <div className="flex items-start justify-between p-6 border-b border-white/10">
                  <div className="flex items-start space-x-4 flex-1">
                    <div className="flex-shrink-0 mt-0.5">
                      {getNotificationIcon(viewNotification.type)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 mb-1 text-xs text-purple-200/75">
                        <span>{t(viewNotificationPresentation.sourceKey)}</span>
                        <span aria-hidden="true">·</span>
                        <span>{t(viewNotificationPresentation.typeKey)}</span>
                      </div>
                      <h3 id={detailTitleId} className="text-xl font-bold text-white mb-1">
                        {viewNotificationText.title}
                      </h3>
                      <p className="text-xs text-gray-400">
                        {formatTime(viewNotification.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteNotificationMutation.mutate(viewNotification.id);
                        setViewNotification(null);
                      }}
                      disabled={deleteNotificationMutation.isPending}
                      className="flex min-h-11 flex-shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-xs text-red-400 transition-all hover:bg-red-500/10 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-50"
                      title={t('notifications.deleteThis')}
                    >
                      {deleteNotificationMutation.isPending ? (
                        <>
                          <div className="w-3 h-3 border-2 border-red-400/30 border-t-red-400 rounded-full animate-spin" />
                          {t('notifications.deleting')}
                        </>
                      ) : (
                        <>
                          <Trash2 className="w-3.5 h-3.5" />
                          {t('notifications.delete')}
                        </>
                      )}
                    </button>
                    <button
                      onClick={() => setViewNotification(null)}
                      className="-mr-2 -mt-2 flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-white/10 hover:text-white"
                      aria-label={t('common.close')}
                    >
                      <X className="w-5 h-5" />
                    </button>
                  </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6 custom-scrollbar">
                  <div className="text-gray-300 whitespace-pre-wrap break-words">
                    {viewNotificationText.message}
                  </div>

                  {/* Link section */}
                  {viewNotification.link && (
                    <div className="mt-6 pt-6 border-t border-white/10">
                      <button
                        type="button"
                        onClick={() => handleOpenLink(viewNotification.link!)}
                        className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-purple-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-300"
                      >
                        {t(viewNotificationPresentation.actionKey)}
                        <ArrowRight className="w-4 h-4" aria-hidden="true" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
          </ModalOverlay>
        )}
      </div>
    );
  }

  // Обычная версия (в хедере)
  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative flex h-11 w-11 items-center justify-center rounded-lg text-gray-300 transition-all hover:bg-white/10 hover:text-white"
        aria-label={unreadCount > 0
          ? `${t('notifications.title')}: ${t('notifications.newCount', { count: unreadCount })}`
          : t('notifications.title')}
        aria-expanded={isOpen}
        aria-controls={panelId}
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          id={panelId}
          role="region"
          aria-label={t('notifications.title')}
          className="app-shell-header-popover fixed mx-auto flex max-h-[70vh] max-w-[calc(100vw-16px)] flex-col overflow-hidden rounded-xl border border-white/20 bg-gradient-to-br from-purple-900 to-indigo-900 shadow-2xl z-[10000] md:absolute md:mx-0 md:max-h-[80vh] md:w-[26rem] md:max-w-none"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-3 md:p-4 border-b border-white/10">
            <h3 className="text-base md:text-lg font-bold text-white">{t('notifications.title')}</h3>
            {unreadCount > 0 && (
              <span className="px-2 py-0.5 md:py-1 bg-purple-600 text-white text-xs font-semibold rounded-full">
                {t('notifications.newCount', { count: unreadCount })}
              </span>
            )}
          </div>

          {/* Notifications List */}
          <div className="overflow-y-auto flex-1">
            {isNotificationsLoading && !notificationsData ? (
              <div className="p-6 md:p-8 text-center text-gray-400" role="status">
                <div className="w-7 h-7 mx-auto mb-3 border-2 border-purple-300/30 border-t-purple-300 rounded-full animate-spin" />
                <p className="text-sm md:text-base">{t('notifications.loading')}</p>
              </div>
            ) : isNotificationsError && notifications.length === 0 ? (
              <div className="p-6 md:p-8 text-center text-gray-400" role="alert">
                <AlertCircle className="w-10 h-10 mx-auto mb-3 text-yellow-400/80" />
                <p className="text-sm md:text-base mb-3">{t('notifications.loadError')}</p>
                <button
                  type="button"
                  onClick={() => void refetch()}
                  className="text-sm font-medium text-purple-300 hover:text-purple-200 transition-colors"
                >
                  {t('notifications.retry')}
                </button>
              </div>
            ) : notifications.length === 0 ? (
              <div className="p-6 md:p-8 text-center text-gray-400">
                <Bell className="w-10 h-10 md:w-12 md:h-12 mx-auto mb-3 opacity-50" />
                <p className="text-sm md:text-base">{t('notifications.empty')}</p>
              </div>
            ) : (
              <NotificationFeedList
                notifications={notifications}
                getText={getNotificationText}
                getIcon={(notification) => getNotificationIcon(notification.type)}
                formatTime={formatTime}
                onOpen={handleNotificationClick}
                onOpenThread={openFeedbackThread}
                onDelete={(ids) => deleteNotificationsMutation.mutate(ids)}
                deletePending={deleteNotificationsMutation.isPending}
              />
            )}
          </div>

          {loadMoreControl}

          {/* Footer */}
          {notifications.length > 0 && (
            <div className="p-2 md:p-3 border-t border-white/10 space-y-2">
              {unreadCount > 0 && (
                <button
                  className="min-h-11 w-full py-2 text-center text-xs text-purple-400 transition-all hover:text-purple-300 md:text-sm"
                  onClick={() => {
                    handleMarkAllAsRead();
                  }}
                  disabled={markAllAsReadMutation.isPending}
                >
                  {markAllAsReadMutation.isPending ? t('notifications.processing') : t('notifications.markAllRead')}
                </button>
              )}
              <button
                className="flex min-h-11 w-full items-center justify-center gap-2 py-2 text-center text-xs text-red-400 transition-all hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-50 md:text-sm"
                onClick={() => {
                  deleteAllNotificationsMutation.mutate();
                }}
                disabled={deleteAllNotificationsMutation.isPending}
              >
                {deleteAllNotificationsMutation.isPending ? (
                  <>
                    <div className="w-4 h-4 border-2 border-red-400/30 border-t-red-400 rounded-full animate-spin" />
                    {t('notifications.clearing')}
                  </>
                ) : (
                  <>
                    <Trash2 className="w-4 h-4" />
                    {t('notifications.clearAll')}
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      )}

      {threadModal}

      {/* Modal for deleted presets */}
      {selectedNotification && (
        <DeletedPresetsModal
          isOpen={!!selectedNotification}
          onClose={() => {
            setSelectedNotification(null);
            queryClient.invalidateQueries({ queryKey: ['notifications', user?.id] });
          }}
          notification={selectedNotification}
        />
      )}

      {/* Modal for viewing notification */}
      {viewNotification && viewNotificationText && viewNotificationPresentation && (
        <ModalOverlay onClose={() => setViewNotification(null)}>
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby={detailTitleId}
              className="bg-gradient-to-br from-purple-900 to-indigo-900 rounded-t-2xl md:rounded-2xl w-full md:max-w-2xl overflow-hidden flex flex-col border-t md:border border-white/20 shadow-2xl max-h-[85vh]"
            >
              {/* Header */}
              <div className="flex items-start justify-between p-4 md:p-6 border-b border-white/10">
                <div className="flex items-start space-x-3 md:space-x-4 flex-1">
                  <div className="flex-shrink-0 mt-0.5">
                    {getNotificationIcon(viewNotification.type)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 mb-1 text-[10px] md:text-xs text-purple-200/75">
                      <span>{t(viewNotificationPresentation.sourceKey)}</span>
                      <span aria-hidden="true">·</span>
                      <span>{t(viewNotificationPresentation.typeKey)}</span>
                    </div>
                    <h3 id={detailTitleId} className="text-base md:text-xl font-bold text-white mb-1">
                      {viewNotificationText.title}
                    </h3>
                    <p className="text-[10px] md:text-xs text-gray-400">
                      {formatTime(viewNotification.created_at)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteNotificationMutation.mutate(viewNotification.id);
                      setViewNotification(null);
                    }}
                    disabled={deleteNotificationMutation.isPending}
                    className="flex min-h-11 flex-shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-xs text-red-400 transition-all hover:bg-red-500/10 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-50"
                    title={t('notifications.deleteThis')}
                  >
                    {deleteNotificationMutation.isPending ? (
                      <>
                        <div className="w-3 h-3 border-2 border-red-400/30 border-t-red-400 rounded-full animate-spin" />
                        {t('notifications.deleting')}
                      </>
                    ) : (
                      <>
                        <Trash2 className="w-3.5 h-3.5" />
                        <span className="hidden md:inline">{t('notifications.delete')}</span>
                      </>
                    )}
                  </button>
                  <button
                    onClick={() => setViewNotification(null)}
                    className="-mr-1 -mt-1 flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-white/10 hover:text-white"
                    aria-label={t('common.close')}
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>

              {/* Content */}
              <div className="flex-1 overflow-y-auto p-4 md:p-6 custom-scrollbar">
                <div className="text-sm md:text-base text-gray-300 whitespace-pre-wrap break-words">
                  {viewNotificationText.message}
                </div>

                {/* Link section */}
                {viewNotification.link && (
                  <div className="mt-4 md:mt-6 pt-4 md:pt-6 border-t border-white/10">
                    <button
                      type="button"
                      onClick={() => handleOpenLink(viewNotification.link!)}
                      className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-purple-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-300"
                    >
                      {t(viewNotificationPresentation.actionKey)}
                      <ArrowRight className="w-4 h-4" aria-hidden="true" />
                    </button>
                  </div>
                )}
              </div>

              {/* Mobile footer with delete */}
              <div className="p-4 border-t border-white/10 md:hidden">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteNotificationMutation.mutate(viewNotification.id);
                    setViewNotification(null);
                  }}
                  disabled={deleteNotificationMutation.isPending}
                  className="w-full flex items-center justify-center gap-2 py-3 text-sm text-red-400 hover:text-red-300 bg-red-500/10 rounded-xl transition-all disabled:opacity-50"
                >
                  <Trash2 className="w-4 h-4" />
                  <span>{t('notifications.deleteOne')}</span>
                </button>
              </div>
            </div>
        </ModalOverlay>
      )}
    </div>
  );
}
