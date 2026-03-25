/** Компонент для управления пользователями */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ModalOverlay } from '../ModalOverlay';
import { Users, Shield, CheckCircle, XCircle, Unlink, Link2, Factory, Check, Award } from 'lucide-react';
import { adminAPI, brandsAPI } from '../../api/client';
import { translateApiError } from '../../utils/translateApiError';
import { Dropdown } from '../Dropdown';
import { ConfirmModal } from '../ConfirmModal';
import { BadgeList, BADGE_CONFIG, type BadgeType } from '../Badge';
import type { User, Brand } from '../../types/api';
import type { AxiosError } from 'axios';

export function AdminUsers() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [page, _setPage] = useState(1);
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
      return adminAPI.linkUserToBrand(userId, brandId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      setSelectedUserIdForBrand(null);
      setSelectedBrandId(null);
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      console.error('Brand linking error:', error);
      // Если операция выполнена (статус 200-299), но есть ошибка в ответе - все равно закрываем модалку
      // и обновляем данные, так как привязка могла произойти
      if ((error?.response?.status ?? 0) >= 200 && (error?.response?.status ?? 0) < 300) {
        queryClient.invalidateQueries({ queryKey: ['admin-users'] });
        setSelectedUserIdForBrand(null);
        setSelectedBrandId(null);
      } else {
        alert(translateApiError(t, error?.response?.data?.detail, t('adminUsers.brandLinkError')));
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

  // Обновление бейджей
  const updateBadgesMutation = useMutation({
    mutationFn: ({ userId, badges }: { userId: number; badges: string[] }) => {
      return adminAPI.updateUserBadges(userId, badges);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      setSelectedUserIdForBadges(null);
      setSelectedUserBadges([]);
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
  const [selectedUserIdForBadges, setSelectedUserIdForBadges] = useState<number | null>(null);
  const [selectedUserBadges, setSelectedUserBadges] = useState<BadgeType[]>([]);

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">{t('adminUsers.loading')}</div>;
  }

  const usersList = users || [];

  const getRoleBadge = (user: User) => {
    if (user.role === 'admin') {
      return <span className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-400 text-xs font-semibold">{t('adminUsers.roleAdmin')}</span>;
    }
    return <span className="px-2 py-1 rounded bg-gray-500/20 text-gray-400 text-xs font-semibold">{t('adminUsers.roleUser')}</span>;
  };

  // Фильтрация уже происходит на бэкенде, но оставляем для совместимости
  const filteredUsers = usersList;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2">{t('adminUsers.title')}</h2>
          <p className="text-gray-400">{t('adminUsers.total')}: {usersList.length}</p>
        </div>

        {/* Фильтры */}
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => setRoleFilter(undefined)}
            className={`px-4 py-2 rounded-lg text-sm transition-all ${
              !roleFilter ? 'bg-purple-600 text-white' : 'bg-white/5 text-gray-300 hover:bg-white/10'
            }`}
          >
            {t('adminUsers.filterAll')}
          </button>
          <button
            onClick={() => setRoleFilter('user')}
            className={`px-4 py-2 rounded-lg text-sm transition-all ${
              roleFilter === 'user' ? 'bg-purple-600 text-white' : 'bg-white/5 text-gray-300 hover:bg-white/10'
            }`}
          >
            {t('adminUsers.filterUsers')}
          </button>
          <button
            onClick={() => setRoleFilter('admin')}
            className={`px-4 py-2 rounded-lg text-sm transition-all ${
              roleFilter === 'admin' ? 'bg-purple-600 text-white' : 'bg-white/5 text-gray-300 hover:bg-white/10'
            }`}
          >
            {t('adminUsers.filterAdmins')}
          </button>
          <button
            onClick={() => setShowOnlyWithBrand(!showOnlyWithBrand)}
            className={`px-4 py-2 rounded-lg text-sm transition-all flex items-center gap-2 ${
              showOnlyWithBrand ? 'bg-purple-600 text-white' : 'bg-white/5 text-gray-300 hover:bg-white/10'
            }`}
          >
            <Unlink className="w-4 h-4" />
            <span>{t('adminUsers.filterWithBrand')}</span>
          </button>
        </div>
      </div>

      {filteredUsers.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Users className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>{t('adminUsers.empty')}</p>
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
                    {user.badges && user.badges.length > 0 && (
                      <BadgeList badges={user.badges as BadgeType[]} size="sm" />
                    )}
                    {!user.active && (
                      <span className="px-2 py-1 rounded bg-red-500/20 text-red-400 text-xs font-semibold">
                        {t('adminUsers.deactivated')}
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
                        {t('adminUsers.representative')}:
                      </span>
                      <span className="px-2 py-1 rounded bg-purple-500/20 text-purple-300 text-sm font-semibold">
                        {user.brand_name || `ID: ${user.brand_id}`}
                      </span>
                      {user.role === 'admin' && (
                        <span className="px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-400 text-xs">
                          ({t('adminUsers.roleAdmin')})
                        </span>
                      )}
                    </div>
                  )}
                  <p className="text-xs text-gray-500 mt-2">
                    {t('adminUsers.created')}: {new Date(user.created_at).toLocaleString('ru-RU')}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {!user.active ? (
                    <button
                      onClick={() => setConfirmActivate({ userId: user.id, username: user.username })}
                      disabled={activateMutation.isPending}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-all disabled:opacity-50 text-sm"
                      title={t('adminUsers.activateTitle')}
                    >
                      <CheckCircle className="w-4 h-4" />
                      <span>{t('adminUsers.activate')}</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => setConfirmDeactivate({ userId: user.id, username: user.username })}
                      disabled={deactivateMutation.isPending}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-all disabled:opacity-50 text-sm"
                      title={t('adminUsers.deactivateTitle')}
                    >
                      <XCircle className="w-4 h-4" />
                      <span>{t('adminUsers.deactivate')}</span>
                    </button>
                  )}
                  {user.role !== 'admin' && (
                    <button
                      onClick={() => setConfirmPromote({ userId: user.id, username: user.username })}
                      disabled={promoteMutation.isPending}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition-all disabled:opacity-50 text-sm"
                      title={t('adminUsers.promoteTitle')}
                    >
                      <Shield className="w-4 h-4" />
                      <span>{t('adminUsers.roleAdmin')}</span>
                    </button>
                  )}
                  {user.role === 'admin' && (
                    <button
                      onClick={() => setConfirmDemote({ userId: user.id, username: user.username })}
                      disabled={demoteMutation.isPending}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-600 hover:bg-gray-700 text-white rounded-lg transition-all disabled:opacity-50 text-sm"
                      title={t('adminUsers.demoteTitle')}
                    >
                      <Shield className="w-4 h-4" />
                      <span>{t('adminUsers.demote')}</span>
                    </button>
                  )}
                  <button
                    onClick={() => {
                      setSelectedUserIdForBadges(user.id);
                      setSelectedUserBadges((user.badges as BadgeType[]) || []);
                    }}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg transition-all text-sm"
                    title={t('adminUsers.manageBadgesTitle')}
                  >
                    <Award className="w-4 h-4" />
                    <span>{t('adminUsers.badges')}</span>
                  </button>
                  {!user.brand_id ? (
                    <button
                      onClick={() => {
                        setSelectedUserIdForBrand(user.id);
                        setSelectedBrandId(null);
                      }}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-all text-sm"
                      title={t('adminUsers.linkBrandTitle')}
                    >
                      <Link2 className="w-4 h-4" />
                      <span>{t('adminUsers.brand')}</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => setConfirmUnlink({ 
                        userId: user.id, 
                        username: user.username,
                        brandName: user.brand_name || `#${user.brand_id}`
                      })}
                      disabled={unlinkBrandMutation.isPending}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-600 hover:bg-orange-700 text-white rounded-lg transition-all disabled:opacity-50 text-sm"
                      title={t('adminUsers.unlinkBrandTitle')}
                    >
                      <Unlink className="w-4 h-4" />
                      <span>{t('adminUsers.unlink')}</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Модальное окно для выбора бренда */}
      {selectedUserIdForBrand && (
        <ModalOverlay onClose={() => { setSelectedUserIdForBrand(null); setSelectedBrandId(null); }}>
          <div
            className="bg-gray-800 rounded-xl p-6 max-w-md w-full border border-white/10 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-xl font-bold text-white mb-4">{t('adminUsers.linkBrandTitle')}</h3>
            <p className="text-gray-400 mb-4">{t('adminUsers.selectBrand')}</p>
            <Dropdown
              value={selectedBrandId || ''}
              options={brandsData?.items.map((brand: Brand) => ({
                value: brand.id,
                label: brand.name,
                icon: brand.verified ? <Check className="w-4 h-4 text-green-400" /> : <Factory className="w-4 h-4 text-gray-400" />,
              })) || []}
              onChange={(value) => setSelectedBrandId(value ? Number(value) : null)}
              placeholder={t('adminUsers.selectBrandPlaceholder')}
              filterable={true}
              className="mb-4"
              emptyMessage={t('adminUsers.brandsNotFound')}
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
                {t('adminUsers.cancel')}
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
                {linkBrandMutation.isPending ? t('adminUsers.linking') : t('adminUsers.link')}
              </button>
            </div>
          </div>
        </ModalOverlay>
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
        title={t('adminUsers.activateTitle')}
        message={t('adminUsers.confirmActivate', { username: confirmActivate?.username })}
        confirmText={t('adminUsers.activate')}
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
        title={t('adminUsers.deactivateTitle')}
        message={t('adminUsers.confirmDeactivate', { username: confirmDeactivate?.username })}
        confirmText={t('adminUsers.deactivate')}
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
        title={t('adminUsers.promoteTitle')}
        message={t('adminUsers.confirmPromote', { username: confirmPromote?.username })}
        confirmText={t('adminUsers.promote')}
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
        title={t('adminUsers.demoteTitle')}
        message={t('adminUsers.confirmDemote', { username: confirmDemote?.username })}
        confirmText={t('adminUsers.demoteConfirm')}
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
        title={t('adminUsers.unlinkBrandTitle')}
        message={t('adminUsers.confirmUnlink', { username: confirmUnlink?.username, brandName: confirmUnlink?.brandName })}
        confirmText={t('adminUsers.unlink')}
        isLoading={unlinkBrandMutation.isPending}
        variant="warning"
        icon={<Unlink className="w-5 h-5" />}
      />

      {/* Модальное окно для управления бейджами */}
      {selectedUserIdForBadges && (
        <ModalOverlay onClose={() => { setSelectedUserIdForBadges(null); setSelectedUserBadges([]); }}>
          <div
            className="bg-gray-800 rounded-xl p-6 max-w-md w-full border border-white/10 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-xl font-bold text-white mb-4">{t('adminUsers.manageBadgesTitle')}</h3>
            <p className="text-gray-400 mb-4">{t('adminUsers.manageBadgesDescription')}</p>
            
            <div className="space-y-2 mb-4 max-h-96 overflow-y-auto">
              {(Object.keys(BADGE_CONFIG) as BadgeType[]).map((badgeType) => {
                const config = BADGE_CONFIG[badgeType];
                const Icon = config.icon;
                const isSelected = selectedUserBadges.includes(badgeType);
                
                // Подробные описания для каждого бейджа
                const descriptions: Record<BadgeType, string> = {
                  founder: t('adminUsers.badgeDesc.founder'),
                  beta_tester: t('adminUsers.badgeDesc.beta_tester'),
                  contributor: t('adminUsers.badgeDesc.contributor'),
                  verified: t('adminUsers.badgeDesc.verified'),
                  early_adopter: t('adminUsers.badgeDesc.early_adopter'),
                  supporter: t('adminUsers.badgeDesc.supporter'),
                };
                
                return (
                  <label
                    key={badgeType}
                    className={`flex items-start space-x-3 p-3 rounded-lg cursor-pointer transition-all ${
                      isSelected 
                        ? 'bg-purple-500/20 border border-purple-500/50' 
                        : 'bg-white/5 border border-white/10 hover:bg-white/10'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedUserBadges([...selectedUserBadges, badgeType]);
                        } else {
                          setSelectedUserBadges(selectedUserBadges.filter(b => b !== badgeType));
                        }
                      }}
                      className="w-4 h-4 text-purple-600 bg-gray-700 border-gray-600 rounded focus:ring-purple-500 mt-0.5"
                    />
                    <Icon className={`w-5 h-5 ${config.color} flex-shrink-0 mt-0.5`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-white font-medium mb-1">{t(config.labelKey)}</div>
                      <div className="text-xs text-gray-300 leading-relaxed">{descriptions[badgeType]}</div>
                    </div>
                  </label>
                );
              })}
            </div>

            <div className="flex gap-2 justify-end">
              <button
                onClick={() => {
                  setSelectedUserIdForBadges(null);
                  setSelectedUserBadges([]);
                }}
                disabled={updateBadgesMutation.isPending}
                className="px-4 py-2 bg-white/5 hover:bg-white/10 text-white rounded-lg transition-all disabled:opacity-50"
              >
                {t('adminUsers.cancel')}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (selectedUserIdForBadges) {
                    updateBadgesMutation.mutate({
                      userId: selectedUserIdForBadges,
                      badges: selectedUserBadges,
                    });
                  }
                }}
                disabled={updateBadgesMutation.isPending}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-all disabled:opacity-50"
              >
                {updateBadgesMutation.isPending ? t('adminUsers.saving') : t('adminUsers.save')}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}


