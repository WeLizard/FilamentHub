/** Компонент для управления пользователями */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Users, Shield, CheckCircle, XCircle, UserPlus, Unlink } from 'lucide-react';
import { adminAPI } from '../../api/client';
import type { User } from '../../types/api';

export function AdminUsers() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [roleFilter, setRoleFilter] = useState<string | undefined>(undefined);

  // Загрузка пользователей
  const { data: users, isLoading } = useQuery({
    queryKey: ['admin-users', page, roleFilter],
    queryFn: () => adminAPI.listUsers({ page, size: 20, role: roleFilter, active_only: false }),
  });

  // Активация пользователя
  const activateMutation = useMutation({
    mutationFn: (userId: number) => adminAPI.activateUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    },
  });

  // Деактивация пользователя
  const deactivateMutation = useMutation({
    mutationFn: (userId: number) => adminAPI.deactivateUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    },
  });

  // Назначение администратором
  const promoteMutation = useMutation({
    mutationFn: (userId: number) => adminAPI.promoteToAdmin(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    },
  });

  // Отвязка от бренда
  const unlinkBrandMutation = useMutation({
    mutationFn: (userId: number) => adminAPI.unlinkUserFromBrand(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    },
  });

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">Загрузка пользователей...</div>;
  }

  const usersList = users || [];

  const getRoleBadge = (role: string) => {
    switch (role) {
      case 'admin':
        return <span className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-400 text-xs font-semibold">Админ</span>;
      case 'brand':
        return <span className="px-2 py-1 rounded bg-green-500/20 text-green-400 text-xs font-semibold">Бренд</span>;
      default:
        return <span className="px-2 py-1 rounded bg-gray-500/20 text-gray-400 text-xs font-semibold">Пользователь</span>;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2">Управление пользователями</h2>
          <p className="text-gray-400">Всего: {usersList.length}</p>
        </div>

        {/* Фильтры */}
        <div className="flex gap-2">
          <button
            onClick={() => setRoleFilter(undefined)}
            className={`px-4 py-2 rounded-lg text-sm transition-all ${
              !roleFilter ? 'bg-purple-600 text-white' : 'bg-white/5 text-gray-300 hover:bg-white/10'
            }`}
          >
            Все
          </button>
          <button
            onClick={() => setRoleFilter('user')}
            className={`px-4 py-2 rounded-lg text-sm transition-all ${
              roleFilter === 'user' ? 'bg-purple-600 text-white' : 'bg-white/5 text-gray-300 hover:bg-white/10'
            }`}
          >
            Пользователи
          </button>
          <button
            onClick={() => setRoleFilter('brand')}
            className={`px-4 py-2 rounded-lg text-sm transition-all ${
              roleFilter === 'brand' ? 'bg-purple-600 text-white' : 'bg-white/5 text-gray-300 hover:bg-white/10'
            }`}
          >
            Бренды
          </button>
          <button
            onClick={() => setRoleFilter('admin')}
            className={`px-4 py-2 rounded-lg text-sm transition-all ${
              roleFilter === 'admin' ? 'bg-purple-600 text-white' : 'bg-white/5 text-gray-300 hover:bg-white/10'
            }`}
          >
            Админы
          </button>
        </div>
      </div>

      {usersList.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Users className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>Нет пользователей для отображения</p>
        </div>
      ) : (
        <div className="space-y-4">
          {usersList.map((user) => (
            <div
              key={user.id}
              className="bg-white/5 rounded-xl p-4 border border-white/10 hover:border-white/20 transition-all"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    <Users className="w-5 h-5 text-purple-400" />
                    <h3 className="text-lg font-semibold text-white">{user.username}</h3>
                    {getRoleBadge(user.role)}
                    {!user.active && (
                      <span className="px-2 py-1 rounded bg-red-500/20 text-red-400 text-xs font-semibold">
                        Деактивирован
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-400 mb-1">{user.email}</p>
                  {user.full_name && (
                    <p className="text-sm text-gray-400 mb-1">{user.full_name}</p>
                  )}
                  {user.brand_id && user.brand_name && (
                    <p className="text-sm text-purple-400 mb-1">
                      Бренд: <span className="font-semibold">{user.brand_name}</span>
                    </p>
                  )}
                  <p className="text-xs text-gray-500 mt-2">
                    Создан: {new Date(user.created_at).toLocaleString('ru-RU')}
                  </p>
                </div>
                <div className="flex items-center space-x-2">
                  {!user.active ? (
                    <button
                      onClick={() => {
                        if (confirm(`Активировать пользователя "${user.username}"?`)) {
                          activateMutation.mutate(user.id);
                        }
                      }}
                      disabled={activateMutation.isPending}
                      className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-all disabled:opacity-50"
                    >
                      <CheckCircle className="w-4 h-4" />
                      <span>Активировать</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        if (confirm(`Деактивировать пользователя "${user.username}"?`)) {
                          deactivateMutation.mutate(user.id);
                        }
                      }}
                      disabled={deactivateMutation.isPending}
                      className="flex items-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-all disabled:opacity-50"
                    >
                      <XCircle className="w-4 h-4" />
                      <span>Деактивировать</span>
                    </button>
                  )}
                  {user.role !== 'admin' && (
                    <button
                      onClick={() => {
                        if (confirm(`Назначить пользователя "${user.username}" администратором?`)) {
                          promoteMutation.mutate(user.id);
                        }
                      }}
                      disabled={promoteMutation.isPending}
                      className="flex items-center space-x-2 px-4 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition-all disabled:opacity-50"
                    >
                      <Shield className="w-4 h-4" />
                      <span>Сделать админом</span>
                    </button>
                  )}
                  {user.role === 'brand' && user.brand_id && (
                    <button
                      onClick={() => {
                        if (confirm(`Отвязать пользователя "${user.username}" от бренда "${user.brand_name || `#${user.brand_id}`}"? Его роль будет изменена на "Пользователь".`)) {
                          unlinkBrandMutation.mutate(user.id);
                        }
                      }}
                      disabled={unlinkBrandMutation.isPending}
                      className="flex items-center space-x-2 px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg transition-all disabled:opacity-50"
                    >
                      <Unlink className="w-4 h-4" />
                      <span>Отвязать от бренда</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


