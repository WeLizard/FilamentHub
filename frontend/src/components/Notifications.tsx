/** Компонент уведомлений с колокольчиком */

import { useState, useRef, useEffect } from 'react';
import { Bell, CheckCircle, XCircle, AlertCircle, Info, Settings, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { notificationsAPI } from '../api/client';
import type { Notification, NotificationType } from '../types/api';
import { DeletedPresetsModal } from './DeletedPresetsModal';

export function Notifications() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [selectedNotification, setSelectedNotification] = useState<Notification | null>(null);

  // Загружаем уведомления
  const { data: notificationsData, refetch } = useQuery({
    queryKey: ['notifications', user?.id],
    queryFn: () => notificationsAPI.list({ page: 1, size: 50 }),
    enabled: !!user,
    refetchInterval: 30000, // Обновляем каждые 30 секунд
  });

  const notifications = notificationsData?.items || [];
  const unreadCount = notificationsData?.unread_count || 0;

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
      default:
        return <Info className="w-5 h-5 text-blue-400" />;
    }
  };

  const handleNotificationClick = (notification: Notification) => {
    // Отмечаем как прочитанное при клике
    if (!notification.read) {
      markAsReadMutation.mutate(notification.id);
    }
    
    // Для уведомлений о локально удалённых пресетах открываем модалку
    if (notification.type === 'preset_locally_deleted') {
      setSelectedNotification(notification);
      setIsOpen(false);
      return;
    }
    
    // Переходим по ссылке, если есть
    if (notification.link) {
      navigate(notification.link);
      setIsOpen(false);
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

    if (diffMins < 1) return 'только что';
    if (diffMins < 60) return `${diffMins} мин назад`;
    if (diffHours < 24) return `${diffHours} ч назад`;
    if (diffDays < 7) return `${diffDays} дн назад`;
    return date.toLocaleDateString('ru-RU');
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative flex items-center justify-center w-10 h-10 rounded-lg text-gray-300 hover:text-white hover:bg-white/10 transition-all"
        aria-label="Уведомления"
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 top-12 w-96 bg-gradient-to-br from-purple-900 to-indigo-900 rounded-xl border border-white/20 shadow-2xl z-[10000] max-h-[80vh] overflow-hidden flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-white/10">
            <h3 className="text-lg font-bold text-white">Уведомления</h3>
            {unreadCount > 0 && (
              <span className="px-2 py-1 bg-purple-600 text-white text-xs font-semibold rounded-full">
                {unreadCount} новых
              </span>
            )}
          </div>

          {/* Notifications List */}
          <div className="overflow-y-auto flex-1">
            {notifications.length === 0 ? (
              <div className="p-8 text-center text-gray-400">
                <Bell className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>Нет уведомлений</p>
              </div>
            ) : (
              <div className="divide-y divide-white/10">
                {notifications.map((notification) => (
                  <div
                    key={notification.id}
                    className={`p-4 hover:bg-white/5 transition-all ${
                      !notification.read ? 'bg-white/5' : ''
                    }`}
                  >
                    <div className="flex items-start space-x-3">
                      <div
                        className="flex-1 min-w-0 cursor-pointer"
                        onClick={() => handleNotificationClick(notification)}
                      >
                        <div className="flex items-start space-x-3">
                          <div className="flex-shrink-0 mt-0.5">
                            {getNotificationIcon(notification.type)}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-semibold text-white mb-1">
                              {notification.title}
                            </p>
                            <p className="text-sm text-gray-300 mb-2">
                              {notification.message}
                            </p>
                            <p className="text-xs text-gray-400">
                              {formatTime(notification.created_at)}
                            </p>
                          </div>
                          {!notification.read && (
                            <div className="w-2 h-2 bg-blue-400 rounded-full flex-shrink-0 mt-2"></div>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteNotificationMutation.mutate(notification.id);
                        }}
                        disabled={deleteNotificationMutation.isPending}
                        className="flex-shrink-0 p-1 rounded hover:bg-white/10 text-gray-400 hover:text-red-400 transition-all"
                        title="Удалить уведомление"
                        aria-label="Удалить уведомление"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          {notifications.length > 0 && unreadCount > 0 && (
            <div className="p-3 border-t border-white/10">
              <button
                className="w-full text-center text-sm text-purple-400 hover:text-purple-300 transition-all"
                onClick={() => {
                  handleMarkAllAsRead();
                }}
                disabled={markAllAsReadMutation.isPending}
              >
                {markAllAsReadMutation.isPending ? 'Обработка...' : 'Отметить все как прочитанные'}
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
    </div>
  );
}

