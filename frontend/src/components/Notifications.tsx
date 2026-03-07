/** Компонент уведомлений с колокольчиком */

import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Bell, CheckCircle, XCircle, AlertCircle, Info, Settings, X, MessageCircle, ExternalLink, Trash2 } from 'lucide-react';
import { createPortal } from 'react-dom';
import { useHeaderVisible } from '../hooks/useHeaderVisible';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { notificationsAPI } from '../api/client';
import type { Notification, NotificationListResponse, NotificationType } from '../types/api';
import { DeletedPresetsModal } from './DeletedPresetsModal';

interface NotificationsProps {
  floating?: boolean; // Плавающая версия для OrcaSlicer (когда нет хедера)
}

export const Notifications: React.FC<NotificationsProps> = ({ floating = false }) => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isHeaderVisible = useHeaderVisible();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [selectedNotification, setSelectedNotification] = useState<Notification | null>(null);
  const [viewNotification, setViewNotification] = useState<Notification | null>(null);
  
  // Для плавающей версии используем внутренний счётчик (обновляется через postMessage от C++)
  const [externalUnreadCount, setExternalUnreadCount] = useState<number | null>(null);

  // Загружаем уведомления
  const { data: notificationsData, refetch } = useQuery({
    queryKey: ['notifications', user?.id],
    queryFn: () => notificationsAPI.list({ page: 1, size: 50 }),
    enabled: !!user,
    refetchInterval: 30000, // Обновляем каждые 30 секунд
  });

  const notifications = notificationsData?.items || [];
  // Для плавающей версии используем внешний счётчик (от C++), иначе счётчик из API
  const unreadCount = floating && externalUnreadCount !== null 
    ? externalUnreadCount 
    : (notificationsData?.unread_count || 0);

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

  // Мутация для удаления всех уведомлений
  const deleteAllNotificationsMutation = useMutation({
    mutationFn: () => notificationsAPI.deleteAll(),
    onSuccess: () => {
      queryClient.setQueryData(['notifications', user?.id], (old: NotificationListResponse | undefined) =>
        old ? { ...old, items: [], total: 0, unread_count: 0 } : old
      );
      queryClient.invalidateQueries({ queryKey: ['notifications', user?.id] });
      setIsOpen(false);
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
      default:
        return <Info className="w-5 h-5 text-blue-400" />;
    }
  };

  const handleNotificationClick = (notification: Notification) => {
    // Отмечаем как прочитанное при клике
    if (!notification.read) {
      markAsReadMutation.mutate(notification.id);
    }
    
    // Для уведомлений о локально удалённых пресетах открываем специальную модалку
    if (notification.type === 'preset_locally_deleted') {
      setSelectedNotification(notification);
      setIsOpen(false);
      return;
    }
    
    // Для всех остальных уведомлений открываем модалку для просмотра
    setViewNotification(notification);
    setIsOpen(false);
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
    return date.toLocaleDateString();
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
    const message = normalizedMessage === messageKey ? notification.message : normalizedMessage;
    return { title, message };
  };

  const viewNotificationText = viewNotification ? getNotificationText(viewNotification) : null;

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
          aria-label={t('notifications.title')}
        >
          <Bell className="w-6 h-6" />
          {unreadCount > 0 && (
            <span className="absolute -top-1 -right-1 w-6 h-6 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center ring-2 ring-purple-900">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>

        {isOpen && (
          <div className="absolute right-0 bottom-full mb-4 w-96 bg-gradient-to-br from-purple-900 to-indigo-900 rounded-xl border border-white/20 shadow-2xl z-[10000] max-h-[80vh] overflow-hidden flex flex-col">
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
              {notifications.length === 0 ? (
                <div className="p-8 text-center text-gray-400">
                  <Bell className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>{t('notifications.empty')}</p>
                </div>
              ) : (
                <div className="divide-y divide-white/10">
                  {notifications.map((notification) => {
                    const { title, message } = getNotificationText(notification);
                    const previewLength = 150;
                    const messagePreview = message.length > previewLength
                      ? message.substring(0, previewLength) + '...'
                      : message;
                    const isLongMessage = message.length > previewLength;
                    const hasLink = !!notification.link;
                    
                    return (
                      <div
                        key={notification.id}
                        className={`p-4 transition-all hover:bg-white/10 cursor-pointer ${
                          !notification.read ? 'bg-white/5' : ''
                        }`}
                        onClick={() => handleNotificationClick(notification)}
                      >
                        <div className="flex items-start space-x-3">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-start space-x-3">
                              <div className="flex-shrink-0 mt-0.5">
                                {getNotificationIcon(notification.type)}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-start justify-between gap-2 mb-1">
                                  <p className="text-sm font-semibold text-white">
                                    {title}
                                  </p>
                                  {!notification.read && (
                                    <div className="w-2 h-2 bg-blue-400 rounded-full flex-shrink-0 mt-1.5"></div>
                                  )}
                                </div>
                                <p className="text-sm text-gray-300 mb-2">
                                  {messagePreview}
                                  {isLongMessage && (
                                    <span className="text-purple-400 ml-1">{t('notifications.clickForFull')}</span>
                                  )}
                                </p>
                                <div className="flex items-center justify-between gap-2">
                                  <p className="text-xs text-gray-400">
                                    {formatTime(notification.created_at)}
                                  </p>
                                </div>
                                {hasLink && (
                                  <a
                                    href={notification.link || '#'}
                                    onClick={(e) => {
                                      e.preventDefault();
                                      e.stopPropagation();
                                      handleOpenLink(notification.link!);
                                    }}
                                    className="block text-xs text-purple-400 hover:text-purple-300 hover:underline mt-1 truncate max-w-full transition-colors"
                                    title={notification.link || undefined}
                                    onMouseEnter={(e) => e.stopPropagation()}
                                    onMouseLeave={(e) => e.stopPropagation()}
                                  >
                                    {notification.link}
                                  </a>
                                )}
                              </div>
                            </div>
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteNotificationMutation.mutate(notification.id);
                            }}
                            disabled={deleteNotificationMutation.isPending}
                            className="flex-shrink-0 p-1 rounded hover:bg-white/10 text-gray-400 hover:text-red-400 transition-all"
                            title={t('notifications.deleteOne')}
                            aria-label={t('notifications.deleteOne')}
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Footer - тот же код что ниже */}
            {notifications.length > 0 && (
              <div className="p-3 border-t border-white/10 space-y-2">
                {unreadCount > 0 && (
                  <button
                    className="w-full text-center text-sm text-purple-400 hover:text-purple-300 transition-all py-2"
                    onClick={() => {
                      handleMarkAllAsRead();
                    }}
                    disabled={markAllAsReadMutation.isPending}
                  >
                    {markAllAsReadMutation.isPending ? t('notifications.processing') : t('notifications.markAllRead')}
                  </button>
                )}
                <button
                  className="w-full flex items-center justify-center gap-2 text-center text-sm text-red-400 hover:text-red-300 transition-all py-2 disabled:opacity-50 disabled:cursor-not-allowed"
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
        {viewNotification && viewNotificationText && createPortal(
          <div
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] overflow-y-auto"
            onClick={() => setViewNotification(null)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                setViewNotification(null);
              }
            }}
          >
            <div className="min-h-full flex items-center justify-center p-4">
              <div
                className="bg-gradient-to-br from-purple-900 to-indigo-900 rounded-2xl max-w-2xl w-full overflow-hidden flex flex-col border border-white/20 shadow-2xl max-h-[85vh]"
                onClick={(e) => e.stopPropagation()}
              >
                {/* Header */}
                <div className="flex items-start justify-between p-6 border-b border-white/10">
                  <div className="flex items-start space-x-4 flex-1">
                    <div className="flex-shrink-0 mt-0.5">
                      {getNotificationIcon(viewNotification.type)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-xl font-bold text-white mb-1">
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
                      className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
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
                      className="flex-shrink-0 text-gray-400 hover:text-white transition-colors p-2 -mt-2 -mr-2"
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
                      <p className="text-sm text-gray-400 mb-2">{t('notifications.link')}</p>
                      <a
                        href={viewNotification.link}
                        onClick={(e) => {
                          e.preventDefault();
                          handleOpenLink(viewNotification.link!);
                        }}
                        className="inline-block text-sm text-purple-400 hover:text-purple-300 hover:underline break-all transition-colors"
                      >
                        {viewNotification.link}
                      </a>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>,
          document.body
        )}
      </div>
    );
  }

  // Обычная версия (в хедере)
  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative flex items-center justify-center w-10 h-10 rounded-lg text-gray-300 hover:text-white hover:bg-white/10 transition-all"
        aria-label={t('notifications.title')}
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="fixed md:absolute inset-x-2 md:inset-x-auto md:right-0 top-16 md:top-12 md:w-96 bg-gradient-to-br from-purple-900 to-indigo-900 rounded-xl border border-white/20 shadow-2xl z-[10000] max-h-[70vh] md:max-h-[80vh] overflow-hidden flex flex-col mx-auto md:mx-0 max-w-[calc(100vw-16px)] md:max-w-none">
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
            {notifications.length === 0 ? (
              <div className="p-6 md:p-8 text-center text-gray-400">
                <Bell className="w-10 h-10 md:w-12 md:h-12 mx-auto mb-3 opacity-50" />
                <p className="text-sm md:text-base">{t('notifications.empty')}</p>
              </div>
            ) : (
              <div className="divide-y divide-white/10">
                {notifications.map((notification) => {
                  const { title, message } = getNotificationText(notification);
                  // Обрезаем текст для предпросмотра (максимум 150 символов)
                  const previewLength = 150;
                  const messagePreview = message.length > previewLength
                    ? message.substring(0, previewLength) + '...'
                    : message;
                  const isLongMessage = message.length > previewLength;
                  const hasLink = !!notification.link;
                  
                  return (
                    <div
                      key={notification.id}
                      className={`p-3 md:p-4 transition-all hover:bg-white/10 cursor-pointer ${
                        !notification.read ? 'bg-white/5' : ''
                      }`}
                      onClick={() => handleNotificationClick(notification)}
                    >
                      <div className="flex items-start space-x-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start space-x-2 md:space-x-3">
                            <div className="flex-shrink-0 mt-0.5">
                              {getNotificationIcon(notification.type)}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-start justify-between gap-2 mb-1">
                                <p className="text-xs md:text-sm font-semibold text-white">
                                  {title}
                                </p>
                                {!notification.read && (
                                  <div className="w-2 h-2 bg-blue-400 rounded-full flex-shrink-0 mt-1.5"></div>
                                )}
                              </div>
                              <p className="text-xs md:text-sm text-gray-300 mb-2">
                                {messagePreview}
                                {isLongMessage && (
                                  <span className="text-purple-400 ml-1">{t('notifications.clickForFull')}</span>
                                )}
                              </p>
                              <div className="flex items-center justify-between gap-2">
                                <p className="text-[10px] md:text-xs text-gray-400">
                                  {formatTime(notification.created_at)}
                                </p>
                              </div>
                              {hasLink && (
                                <a
                                  href={notification.link || '#'}
                                  onClick={(e) => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    handleOpenLink(notification.link!);
                                  }}
                                  className="block text-xs text-purple-400 hover:text-purple-300 hover:underline mt-1 truncate max-w-full transition-colors"
                                  title={notification.link || undefined}
                                  onMouseEnter={(e) => e.stopPropagation()}
                                  onMouseLeave={(e) => e.stopPropagation()}
                                >
                                  {notification.link}
                                </a>
                              )}
                            </div>
                          </div>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteNotificationMutation.mutate(notification.id);
                          }}
                          disabled={deleteNotificationMutation.isPending}
                          className="flex-shrink-0 p-1 rounded hover:bg-white/10 text-gray-400 hover:text-red-400 transition-all"
                          title={t('notifications.deleteOne')}
                          aria-label={t('notifications.deleteOne')}
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Footer */}
          {notifications.length > 0 && (
            <div className="p-2 md:p-3 border-t border-white/10 space-y-2">
              {unreadCount > 0 && (
                <button
                  className="w-full text-center text-xs md:text-sm text-purple-400 hover:text-purple-300 transition-all py-2"
                  onClick={() => {
                    handleMarkAllAsRead();
                  }}
                  disabled={markAllAsReadMutation.isPending}
                >
                  {markAllAsReadMutation.isPending ? t('notifications.processing') : t('notifications.markAllRead')}
                </button>
              )}
              <button
                className="w-full flex items-center justify-center gap-2 text-center text-xs md:text-sm text-red-400 hover:text-red-300 transition-all py-2 disabled:opacity-50 disabled:cursor-not-allowed"
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
      {viewNotification && viewNotificationText && createPortal(
        <div
          className={`fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] overflow-y-auto ${isHeaderVisible ? 'pt-[72px] md:pt-[88px]' : ''}`}
          onClick={() => setViewNotification(null)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              setViewNotification(null);
            }
          }}
        >
          <div className="min-h-full flex items-end md:items-center justify-center p-0 md:p-4">
            <div
              className="bg-gradient-to-br from-purple-900 to-indigo-900 rounded-t-2xl md:rounded-2xl w-full md:max-w-2xl overflow-hidden flex flex-col border-t md:border border-white/20 shadow-2xl max-h-[85vh]"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="flex items-start justify-between p-4 md:p-6 border-b border-white/10">
                <div className="flex items-start space-x-3 md:space-x-4 flex-1">
                  <div className="flex-shrink-0 mt-0.5">
                    {getNotificationIcon(viewNotification.type)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-base md:text-xl font-bold text-white mb-1">
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
                    className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
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
                    className="flex-shrink-0 text-gray-400 hover:text-white transition-colors p-2 -mt-1 -mr-1"
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
                    <p className="text-xs md:text-sm text-gray-400 mb-2">{t('notifications.link')}</p>
                    <a
                      href={viewNotification.link}
                      onClick={(e) => {
                        e.preventDefault();
                        handleOpenLink(viewNotification.link!);
                      }}
                      className="inline-block text-xs md:text-sm text-purple-400 hover:text-purple-300 hover:underline break-all transition-colors"
                    >
                      {viewNotification.link}
                    </a>
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
            </div>
        </div>,
        document.body
      )}
    </div>
  );
}
