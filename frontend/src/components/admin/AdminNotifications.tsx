/** Компонент для управления уведомлениями и рассылками (массовые и конкретным пользователям) */

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Send, Users, UserCheck, AlertCircle, CheckCircle, Link as LinkIcon } from 'lucide-react';
import { adminNotificationsAPI, adminAPI } from '../../api/client';
import { useQuery } from '@tanstack/react-query';
import { toast } from '../Toast';

type NotificationMode = 'broadcast' | 'specific';

export function AdminNotifications() {
  const [mode, setMode] = useState<NotificationMode>('broadcast');
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [link, setLink] = useState('');
  const [activeOnly, setActiveOnly] = useState(true);
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([]);
  const [userSearch, setUserSearch] = useState('');

  // Загрузка пользователей для выбора
  const { data: usersData, isLoading: isLoadingUsers } = useQuery({
    queryKey: ['admin-users-for-notifications', userSearch],
    queryFn: () => adminAPI.listUsers({
      page: 1,
      size: 100,
      active_only: true,
    }),
  });

  const users = Array.isArray(usersData) ? usersData : [];
  
  // Фильтруем пользователей по поиску
  const filteredUsers = userSearch
    ? users.filter((user) =>
        user.username.toLowerCase().includes(userSearch.toLowerCase()) ||
        user.email.toLowerCase().includes(userSearch.toLowerCase()) ||
        user.full_name?.toLowerCase().includes(userSearch.toLowerCase())
      )
    : users.slice(0, 50); // Показываем первые 50 для производительности

  // Массовая рассылка
  const broadcastMutation = useMutation({
    mutationFn: () => adminNotificationsAPI.broadcast({
      title: title.trim(),
      message: message.trim(),
      link: link.trim() || null,
      active_only: activeOnly,
    }),
    onSuccess: (data) => {
      toast.success(`${data.message} (отправлено ${data.count} пользователям)`, 5000);
      setTitle('');
      setMessage('');
      setLink('');
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || error?.message || 'Не удалось отправить уведомление', 6000);
    },
  });

  // Отправка конкретным пользователям
  const sendToSpecificMutation = useMutation({
    mutationFn: () => adminAPI.sendNotification({
      user_ids: selectedUserIds,
      title: title.trim(),
      message: message.trim(),
      link: link.trim() || null,
    }),
    onSuccess: (data) => {
      toast.success(`${data.message} (отправлено ${data.count} пользователям)`, 5000);
      setTitle('');
      setMessage('');
      setLink('');
      setSelectedUserIds([]);
      setUserSearch('');
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || error?.message || 'Не удалось отправить уведомление', 6000);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !message.trim()) {
      toast.warning('Заполните заголовок и сообщение', 4000);
      return;
    }

    if (mode === 'broadcast') {
      if (!confirm(`Отправить сообщение всем активным пользователям?${!activeOnly ? ' (включая неактивных)' : ''}`)) {
        return;
      }
      broadcastMutation.mutate();
    } else {
      if (selectedUserIds.length === 0) {
        toast.warning('Выберите хотя бы одного пользователя', 4000);
        return;
      }
      if (!confirm(`Отправить сообщение ${selectedUserIds.length} выбранным пользователям?`)) {
        return;
      }
      sendToSpecificMutation.mutate();
    }
  };

  const toggleUserSelection = (userId: number) => {
    setSelectedUserIds((prev) =>
      prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId]
    );
  };

  const isSubmitting = broadcastMutation.isPending || sendToSpecificMutation.isPending;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-2 flex items-center gap-2">
          <Send className="w-6 h-6 text-purple-400" />
          Управление уведомлениями
        </h2>
        <p className="text-gray-300 text-sm">
          Отправляйте сообщения всем пользователям или выбранным пользователям. Все уведомления сохраняются в системе.
        </p>
      </div>

      {/* Режимы */}
      <div className="flex gap-4 border-b border-white/10 pb-4">
        <button
          onClick={() => {
            setMode('broadcast');
            setSelectedUserIds([]);
          }}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
            mode === 'broadcast'
              ? 'bg-purple-600 text-white'
              : 'bg-white/5 text-gray-300 hover:bg-white/10'
          }`}
        >
          <Users className="w-4 h-4" />
          <span>Массовая рассылка</span>
        </button>
        <button
          onClick={() => setMode('specific')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
            mode === 'specific'
              ? 'bg-purple-600 text-white'
              : 'bg-white/5 text-gray-300 hover:bg-white/10'
          }`}
        >
          <UserCheck className="w-4 h-4" />
          <span>Конкретным пользователям</span>
        </button>
      </div>

      {/* Форма */}
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Заголовок */}
        <div>
          <label htmlFor="notification-title" className="block text-sm font-medium text-gray-300 mb-2">
            Заголовок *
          </label>
          <input
            id="notification-title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            maxLength={200}
            placeholder="Например: Обновление платформы FilamentHub"
            className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            disabled={isSubmitting}
          />
        </div>

        {/* Сообщение */}
        <div>
          <label htmlFor="notification-message" className="block text-sm font-medium text-gray-300 mb-2">
            Сообщение *
          </label>
          <textarea
            id="notification-message"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            required
            rows={6}
            placeholder="Текст сообщения для пользователей..."
            className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none custom-scrollbar"
            disabled={isSubmitting}
          />
        </div>

        {/* Ссылка (опционально) */}
        <div>
          <label htmlFor="notification-link" className="block text-sm font-medium text-gray-300 mb-2 flex items-center gap-2">
            <LinkIcon className="w-4 h-4" />
            Ссылка (опционально)
          </label>
          <input
            id="notification-link"
            type="text"
            value={link}
            onChange={(e) => setLink(e.target.value)}
            maxLength={500}
            placeholder="/profile или https://example.com"
            className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            disabled={isSubmitting}
          />
          <p className="text-xs text-gray-400 mt-1">Пользователи смогут кликнуть на уведомление для перехода по ссылке</p>
        </div>

        {/* Настройки для массовой рассылки */}
        {mode === 'broadcast' && (
          <div className="flex items-center gap-3 p-4 bg-white/5 rounded-lg border border-white/10">
            <input
              type="checkbox"
              id="active-only"
              checked={activeOnly}
              onChange={(e) => setActiveOnly(e.target.checked)}
              className="w-4 h-4 rounded border-white/20 bg-white/5 text-purple-600 focus:ring-purple-500"
              disabled={isSubmitting}
            />
            <label htmlFor="active-only" className="text-sm text-gray-300 cursor-pointer">
              Отправлять только активным пользователям
            </label>
            {!activeOnly && (
              <span className="text-xs text-yellow-400 ml-2">⚠️ Включая неактивных пользователей</span>
            )}
          </div>
        )}

        {/* Выбор пользователей для конкретной рассылки */}
        {mode === 'specific' && (
          <div className="space-y-3">
            <label className="block text-sm font-medium text-gray-300">
              Выберите пользователей ({selectedUserIds.length} выбрано) *
            </label>
            
            {/* Поиск пользователей */}
            <input
              type="text"
              value={userSearch}
              onChange={(e) => setUserSearch(e.target.value)}
              placeholder="Поиск по имени, email, username..."
              className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              disabled={isSubmitting}
            />

            {/* Список пользователей */}
            <div className="bg-white/5 border border-white/10 rounded-lg p-4 max-h-64 overflow-y-auto custom-scrollbar">
              {isLoadingUsers ? (
                <div className="text-center py-4 text-gray-400">
                  <div className="w-6 h-6 border-2 border-purple-500/30 border-t-purple-500 rounded-full animate-spin mx-auto mb-2" />
                  Загрузка пользователей...
                </div>
              ) : filteredUsers.length === 0 ? (
                <div className="text-center py-4 text-gray-400">
                  {users.length === 0 ? 'Пользователи не найдены' : 'Пользователи не найдены по вашему запросу'}
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredUsers.map((user) => {
                    const isSelected = selectedUserIds.includes(user.id);
                    return (
                      <label
                        key={user.id}
                        className={`flex items-center gap-3 p-2 rounded-lg cursor-pointer transition-all ${
                          isSelected
                            ? 'bg-purple-500/20 border border-purple-500/40'
                            : 'hover:bg-white/10 border border-transparent'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleUserSelection(user.id)}
                          className="w-4 h-4 rounded border-white/20 bg-white/5 text-purple-600 focus:ring-purple-500"
                          disabled={isSubmitting}
                        />
                        <div className="flex-1">
                          <div className="text-sm text-white">
                            {user.full_name || user.username} {user.full_name && <span className="text-gray-400">(@{user.username})</span>}
                          </div>
                          <div className="text-xs text-gray-400">{user.email}</div>
                        </div>
                        {user.role === 'admin' && (
                          <span className="px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-400 text-xs">Admin</span>
                        )}
                      </label>
                    );
                  })}
                </div>
              )}
              
              {users.length > filteredUsers.length && (
                <div className="text-xs text-gray-400 mt-2 text-center">
                  Показано {filteredUsers.length} из {users.length}. Используйте поиск для фильтрации.
                </div>
              )}
            </div>

            {selectedUserIds.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm text-gray-300">Выбрано:</span>
                {selectedUserIds.map((userId) => {
                  const user = users.find((u) => u.id === userId);
                  return (
                    <span
                      key={userId}
                      className="px-2 py-1 rounded bg-purple-500/20 text-purple-300 text-xs flex items-center gap-1"
                    >
                      {user?.username || `#${userId}`}
                      <button
                        type="button"
                        onClick={() => toggleUserSelection(userId)}
                        className="hover:text-white"
                        disabled={isSubmitting}
                      >
                        ×
                      </button>
                    </span>
                  );
                })}
                <button
                  type="button"
                  onClick={() => setSelectedUserIds([])}
                  className="text-xs text-gray-400 hover:text-white"
                  disabled={isSubmitting}
                >
                  Очистить все
                </button>
              </div>
            )}
          </div>
        )}

        {/* Информация */}
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-blue-300">
              <p className="font-medium mb-1">Информация об уведомлениях:</p>
              <ul className="list-disc list-inside space-y-1 text-xs">
                <li>Все уведомления сохраняются в системе и доступны пользователям в разделе уведомлений</li>
                <li>Пользователи получат уведомление с вашим сообщением</li>
                {mode === 'broadcast' && (
                  <li>Массовая рассылка отправляется {activeOnly ? 'всем активным' : 'всем'} пользователям</li>
                )}
                {mode === 'specific' && (
                  <li>Сообщение будет отправлено только выбранным пользователям ({selectedUserIds.length})</li>
                )}
                {link && <li>При клике на уведомление пользователь перейдет по ссылке: {link}</li>}
              </ul>
            </div>
          </div>
        </div>

        {/* Кнопка отправки */}
        <div className="flex items-center justify-end gap-3 pt-4 border-t border-white/10">
          <button
            type="submit"
            disabled={isSubmitting || !title.trim() || !message.trim() || (mode === 'specific' && selectedUserIds.length === 0)}
            className="px-6 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isSubmitting ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Отправка...
              </>
            ) : (
              <>
                <Send className="w-4 h-4" />
                {mode === 'broadcast' ? 'Отправить всем' : `Отправить ${selectedUserIds.length} пользователям`}
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}

