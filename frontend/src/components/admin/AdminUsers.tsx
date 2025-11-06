/** Компонент для управления пользователями */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createPortal } from 'react-dom';
import { Users, Shield, CheckCircle, XCircle, Unlink, Link2, Factory, Check } from 'lucide-react';
import { adminAPI, brandsAPI } from '../../api/client';
import { Dropdown } from '../Dropdown';
import { ConfirmModal } from '../ConfirmModal';
import type { User, Brand } from '../../types/api';

export function AdminUsers() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [roleFilter, setRoleFilter] = useState<string | undefined>(undefined);
  const [showOnlyWithBrand, setShowOnlyWithBrand] = useState(false);

  // Загрузка пользователей
  const { data: users, isLoading } = useQuery({
    queryKey: ['admin-users', page, roleFilter, showOnlyWithBrand],
    queryFn: () => adminAPI.listUsers({ 
      page, 
      size: 20, 
      role: roleFilter, 
      active_only: false,
      with_brand: showOnlyWithBrand ? true : undefined,
    }),
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

  // Отзыв прав администратора
  const demoteMutation = useMutation({
    mutationFn: (userId: number) => adminAPI.demoteToUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    },
  });

  // Привязка к бренду
  const linkBrandMutation = useMutation({
    mutationFn: ({ userId, brandId }: { userId: number; brandId: number }) => {
      console.log('Вызываем API linkUserToBrand:', { userId, brandId });
      return adminAPI.linkUserToBrand(userId, brandId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      setSelectedUserIdForBrand(null);
      setSelectedBrandId(null);
    },
    onError: (error: any) => {
      console.error('Ошибка привязки к бренду:', error);
      // Если операция выполнена (статус 200-299), но есть ошибка в ответе - все равно закрываем модалку
      // и обновляем данные, так как привязка могла произойти
      if (error?.response?.status >= 200 && error?.response?.status < 300) {
        queryClient.invalidateQueries({ queryKey: ['admin-users'] });
        setSelectedUserIdForBrand(null);
        setSelectedBrandId(null);
      } else {
        alert(error?.response?.data?.detail || error?.message || 'Ошибка при привязке к бренду');
      }
    },
  });

  // Отвязка от бренда
  const unlinkBrandMutation = useMutation({
    mutationFn: (userId: number) => adminAPI.unlinkUserFromBrand(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    },
  });

  // Загрузка брендов для выбора
  const { data: brandsData } = useQuery({
    queryKey: ['brands-for-link'],
    queryFn: () => brandsAPI.list({ active_only: true, page: 1, size: 100 }),
  });

  const [selectedUserIdForBrand, setSelectedUserIdForBrand] = useState<number | null>(null);
  const [selectedBrandId, setSelectedBrandId] = useState<number | null>(null);
  
  // Состояния для модалок подтверждения
  const [confirmActivate, setConfirmActivate] = useState<{ userId: number; username: string } | null>(null);
  const [confirmDeactivate, setConfirmDeactivate] = useState<{ userId: number; username: string } | null>(null);
  const [confirmPromote, setConfirmPromote] = useState<{ userId: number; username: string } | null>(null);
  const [confirmDemote, setConfirmDemote] = useState<{ userId: number; username: string } | null>(null);
  const [confirmUnlink, setConfirmUnlink] = useState<{ userId: number; username: string; brandName: string } | null>(null);

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">Загрузка пользователей...</div>;
  }

  const usersList = users || [];

  const getRoleBadge = (user: User) => {
    if (user.role === 'admin') {
      return <span className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-400 text-xs font-semibold">Админ</span>;
    }
    return <span className="px-2 py-1 rounded bg-gray-500/20 text-gray-400 text-xs font-semibold">Пользователь</span>;
  };

  // Фильтрация уже происходит на бэкенде, но оставляем для совместимости
  const filteredUsers = usersList;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2">Управление пользователями</h2>
          <p className="text-gray-400">Всего: {usersList.length}</p>
        </div>

        {/* Фильтры */}
        <div className="flex gap-2 flex-wrap">
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
            onClick={() => setRoleFilter('admin')}
            className={`px-4 py-2 rounded-lg text-sm transition-all ${
              roleFilter === 'admin' ? 'bg-purple-600 text-white' : 'bg-white/5 text-gray-300 hover:bg-white/10'
            }`}
          >
            Админы
          </button>
          <button
            onClick={() => setShowOnlyWithBrand(!showOnlyWithBrand)}
            className={`px-4 py-2 rounded-lg text-sm transition-all flex items-center gap-2 ${
              showOnlyWithBrand ? 'bg-purple-600 text-white' : 'bg-white/5 text-gray-300 hover:bg-white/10'
            }`}
          >
            <Unlink className="w-4 h-4" />
            <span>С привязкой к бренду</span>
          </button>
        </div>
      </div>

      {filteredUsers.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Users className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>Нет пользователей для отображения</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredUsers.map((user) => (
            <div
              key={user.id}
              className="bg-white/5 rounded-xl p-4 border border-white/10 hover:border-white/20 transition-all"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    <Users className="w-5 h-5 text-purple-400" />
                    <h3 className="text-lg font-semibold text-white">{user.username}</h3>
                    {getRoleBadge(user)}
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
                  {user.brand_id && (
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm text-purple-400">
                        Представитель:
                      </span>
                      <span className="px-2 py-1 rounded bg-purple-500/20 text-purple-300 text-sm font-semibold">
                        {user.brand_name || `ID: ${user.brand_id}`}
                      </span>
                      {user.role === 'admin' && (
                        <span className="px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-400 text-xs">
                          (Админ)
                        </span>
                      )}
                    </div>
                  )}
                  <p className="text-xs text-gray-500 mt-2">
                    Создан: {new Date(user.created_at).toLocaleString('ru-RU')}
                  </p>
                </div>
                <div className="flex items-center space-x-2">
                  {!user.active ? (
                    <button
                      onClick={() => setConfirmActivate({ userId: user.id, username: user.username })}
                      disabled={activateMutation.isPending}
                      className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-all disabled:opacity-50"
                    >
                      <CheckCircle className="w-4 h-4" />
                      <span>Активировать</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => setConfirmDeactivate({ userId: user.id, username: user.username })}
                      disabled={deactivateMutation.isPending}
                      className="flex items-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-all disabled:opacity-50"
                    >
                      <XCircle className="w-4 h-4" />
                      <span>Деактивировать</span>
                    </button>
                  )}
                  {user.role !== 'admin' && (
                    <button
                      onClick={() => setConfirmPromote({ userId: user.id, username: user.username })}
                      disabled={promoteMutation.isPending}
                      className="flex items-center space-x-2 px-4 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition-all disabled:opacity-50"
                    >
                      <Shield className="w-4 h-4" />
                      <span>Сделать админом</span>
                    </button>
                  )}
                  {user.role === 'admin' && (
                    <button
                      onClick={() => setConfirmDemote({ userId: user.id, username: user.username })}
                      disabled={demoteMutation.isPending}
                      className="flex items-center space-x-2 px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg transition-all disabled:opacity-50"
                      title="Отозвать права администратора"
                    >
                      <Shield className="w-4 h-4" />
                      <span>Отозвать админку</span>
                    </button>
                  )}
                  {!user.brand_id ? (
                    <button
                      onClick={() => {
                        setSelectedUserIdForBrand(user.id);
                        setSelectedBrandId(null);
                      }}
                      className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-all"
                    >
                      <Link2 className="w-4 h-4" />
                      <span>Привязать к бренду</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => setConfirmUnlink({ 
                        userId: user.id, 
                        username: user.username,
                        brandName: user.brand_name || `#${user.brand_id}`
                      })}
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

      {/* Модальное окно для выбора бренда */}
      {selectedUserIdForBrand && createPortal(
        <div 
          className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setSelectedUserIdForBrand(null);
              setSelectedBrandId(null);
            }
          }}
        >
          <div 
            className="bg-gray-800 rounded-xl p-6 max-w-md w-full border border-white/10 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-xl font-bold text-white mb-4">Привязать к бренду</h3>
            <p className="text-gray-400 mb-4">Выберите бренд для привязки:</p>
            <Dropdown
              value={selectedBrandId || ''}
              options={brandsData?.items.map((brand: Brand) => ({
                value: brand.id,
                label: brand.name,
                icon: brand.verified ? <Check className="w-4 h-4 text-green-400" /> : <Factory className="w-4 h-4 text-gray-400" />,
              })) || []}
              onChange={(value) => setSelectedBrandId(value ? Number(value) : null)}
              placeholder="Выберите бренд..."
              filterable={true}
              className="mb-4"
              emptyMessage="Бренды не найдены"
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => {
                  setSelectedUserIdForBrand(null);
                  setSelectedBrandId(null);
                }}
                disabled={linkBrandMutation.isPending}
                className="px-4 py-2 bg-white/5 hover:bg-white/10 text-white rounded-lg transition-all disabled:opacity-50"
              >
                Отмена
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (selectedBrandId && selectedUserIdForBrand) {
                    linkBrandMutation.mutate({
                      userId: selectedUserIdForBrand,
                      brandId: selectedBrandId,
                    });
                  }
                }}
                disabled={!selectedBrandId || !selectedUserIdForBrand || linkBrandMutation.isPending}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-all disabled:opacity-50"
              >
                {linkBrandMutation.isPending ? 'Привязка...' : 'Привязать'}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Модалки подтверждения */}
      <ConfirmModal
        isOpen={!!confirmActivate}
        onClose={() => setConfirmActivate(null)}
        onConfirm={() => {
          if (confirmActivate) {
            activateMutation.mutate(confirmActivate.userId);
            setConfirmActivate(null);
          }
        }}
        title="Активировать пользователя"
        message={`Вы уверены, что хотите активировать пользователя "${confirmActivate?.username}"?`}
        confirmText="Активировать"
        isLoading={activateMutation.isPending}
        variant="success"
        icon={<CheckCircle className="w-5 h-5" />}
      />

      <ConfirmModal
        isOpen={!!confirmDeactivate}
        onClose={() => setConfirmDeactivate(null)}
        onConfirm={() => {
          if (confirmDeactivate) {
            deactivateMutation.mutate(confirmDeactivate.userId);
            setConfirmDeactivate(null);
          }
        }}
        title="Деактивировать пользователя"
        message={`Вы уверены, что хотите деактивировать пользователя "${confirmDeactivate?.username}"?`}
        confirmText="Деактивировать"
        isLoading={deactivateMutation.isPending}
        variant="danger"
        icon={<XCircle className="w-5 h-5" />}
      />

      <ConfirmModal
        isOpen={!!confirmPromote}
        onClose={() => setConfirmPromote(null)}
        onConfirm={() => {
          if (confirmPromote) {
            promoteMutation.mutate(confirmPromote.userId);
            setConfirmPromote(null);
          }
        }}
        title="Назначить администратором"
        message={`Вы уверены, что хотите назначить пользователя "${confirmPromote?.username}" администратором?`}
        confirmText="Назначить"
        isLoading={promoteMutation.isPending}
        variant="warning"
        icon={<Shield className="w-5 h-5" />}
      />

      <ConfirmModal
        isOpen={!!confirmDemote}
        onClose={() => setConfirmDemote(null)}
        onConfirm={() => {
          if (confirmDemote) {
            demoteMutation.mutate(confirmDemote.userId);
            setConfirmDemote(null);
          }
        }}
        title="Отозвать права администратора"
        message={`Вы уверены, что хотите отозвать права администратора у пользователя "${confirmDemote?.username}"?`}
        confirmText="Отозвать"
        isLoading={demoteMutation.isPending}
        variant="warning"
        icon={<Shield className="w-5 h-5" />}
      />

      <ConfirmModal
        isOpen={!!confirmUnlink}
        onClose={() => setConfirmUnlink(null)}
        onConfirm={() => {
          if (confirmUnlink) {
            unlinkBrandMutation.mutate(confirmUnlink.userId);
            setConfirmUnlink(null);
          }
        }}
        title="Отвязать от бренда"
        message={`Вы уверены, что хотите отвязать пользователя "${confirmUnlink?.username}" от бренда "${confirmUnlink?.brandName}"?`}
        confirmText="Отвязать"
        isLoading={unlinkBrandMutation.isPending}
        variant="warning"
        icon={<Unlink className="w-5 h-5" />}
      />
    </div>
  );
}


