/** Компонент для управления пользователями */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ModalOverlay } from '../ModalOverlay';
import {
  Award,
  Calculator,
  Check,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  CircleOff,
  Factory,
  Link2,
  Search,
  Shield,
  Unlink,
  UserRound,
  Users,
  Trash2,
  XCircle,
} from 'lucide-react';
import { adminAPI, brandsAPI } from '../../api/client';
import { translateApiError } from '../../utils/translateApiError';
import { Dropdown } from '../Dropdown';
import { ConfirmModal } from '../ConfirmModal';
import { ACHIEVEMENT_CONFIG, AchievementBadge } from '../Badge';
import { toast } from '../Toast';
import type { AchievementCode, Brand } from '../../types/api';
import type { AxiosError } from 'axios';
import { useDebounce } from '../../hooks/useDebounce';

const isAchievementCode = (code: string): code is AchievementCode =>
  Object.prototype.hasOwnProperty.call(ACHIEVEMENT_CONFIG, code);

export function AdminUsers() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [roleFilter, setRoleFilter] = useState<string | undefined>(undefined);
  const [showOnlyWithBrand, setShowOnlyWithBrand] = useState(false);
  const [search, setSearch] = useState('');
  const [selectedAchievementUser, setSelectedAchievementUser] = useState<{
    id: number;
    username: string;
  } | null>(null);
  const [selectedAchievementCode, setSelectedAchievementCode] = useState<AchievementCode | ''>('');
  const [achievementReason, setAchievementReason] = useState('');
  const [revokeAchievementCode, setRevokeAchievementCode] = useState<AchievementCode | null>(null);
  const debouncedSearch = useDebounce(search.trim(), 300);

  useEffect(() => {
    setPage(1);
  }, [roleFilter, showOnlyWithBrand, debouncedSearch, pageSize]);

  // Загрузка пользователей
  const { data: usersPage, isLoading, isFetching } = useQuery({
    queryKey: ['admin-users', page, pageSize, roleFilter, showOnlyWithBrand, debouncedSearch],
    queryFn: () => adminAPI.listUsers({ 
      page, 
      size: pageSize,
      role: roleFilter, 
      active_only: false,
      with_brand: showOnlyWithBrand ? true : undefined,
      search: debouncedSearch || undefined,
    }),
    placeholderData: (previousData) => previousData,
  });

  const showActionError = (
    error: AxiosError<{ detail: unknown }>,
    fallbackKey: string,
  ) => {
    toast.error(
      translateApiError(t, error.response?.data?.detail, t(fallbackKey)),
      5000,
      'admin-users-action',
    );
  };

  const showActionSuccess = (message: string) => {
    toast.success(message, 3500, 'admin-users-action');
  };

  // Активация пользователя
  const activateMutation = useMutation({
    mutationFn: (userId: number) => adminAPI.activateUser(userId),
    onSuccess: (updatedUser) => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      showActionSuccess(t('adminUsers.feedback.activateSuccess', { username: updatedUser.username }));
    },
    onError: (error: AxiosError<{ detail: unknown }>) =>
      showActionError(error, 'adminUsers.feedback.activateError'),
  });

  // Деактивация пользователя
  const deactivateMutation = useMutation({
    mutationFn: (userId: number) => adminAPI.deactivateUser(userId),
    onSuccess: (updatedUser) => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      showActionSuccess(t('adminUsers.feedback.deactivateSuccess', { username: updatedUser.username }));
    },
    onError: (error: AxiosError<{ detail: unknown }>) =>
      showActionError(error, 'adminUsers.feedback.deactivateError'),
  });

  // Удаление аккаунта по требованию человека: закон обязывает его исполнить,
  // а отключение аккаунта ничего не стирает.
  const eraseMutation = useMutation({
    mutationFn: (userId: number) => adminAPI.deleteUserAccount(userId, true),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      showActionSuccess(t('adminUsers.feedback.eraseSuccess'));
    },
    onError: (error: AxiosError<{ detail: unknown }>) =>
      showActionError(error, 'adminUsers.feedback.eraseError'),
  });


  // Комплиментарный Pro-доступ к калькулятору (выдать/отозвать)
  const proAccessMutation = useMutation({
    mutationFn: ({ userId, grant }: { userId: number; grant: boolean }) =>
      adminAPI.setUserProAccess(userId, grant),
    onSuccess: (updatedUser, variables) => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      showActionSuccess(t(
        variables.grant
          ? 'adminUsers.feedback.proGrantSuccess'
          : 'adminUsers.feedback.proRevokeSuccess',
        { username: updatedUser.username },
      ));
    },
    onError: (error: AxiosError<{ detail: unknown }>, variables) =>
      showActionError(
        error,
        variables.grant
          ? 'adminUsers.feedback.proGrantError'
          : 'adminUsers.feedback.proRevokeError',
      ),
  });

  // Назначение администратором
  const promoteMutation = useMutation({
    mutationFn: (userId: number) => adminAPI.promoteToAdmin(userId),
    onSuccess: (updatedUser) => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      showActionSuccess(t('adminUsers.feedback.promoteSuccess', { username: updatedUser.username }));
    },
    onError: (error: AxiosError<{ detail: unknown }>) =>
      showActionError(error, 'adminUsers.feedback.promoteError'),
  });

  // Отзыв прав администратора
  const demoteMutation = useMutation({
    mutationFn: (userId: number) => adminAPI.demoteToUser(userId),
    onSuccess: (updatedUser) => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      showActionSuccess(t('adminUsers.feedback.demoteSuccess', { username: updatedUser.username }));
    },
    onError: (error: AxiosError<{ detail: unknown }>) =>
      showActionError(error, 'adminUsers.feedback.demoteError'),
  });

  // Привязка к бренду
  const linkBrandMutation = useMutation({
    mutationFn: ({ userId, brandId }: { userId: number; brandId: number }) => {
      return adminAPI.linkUserToBrand(userId, brandId);
    },
    onSuccess: (updatedUser) => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      setSelectedUserIdForBrand(null);
      setSelectedBrandId(null);
      showActionSuccess(t('adminUsers.feedback.brandLinkSuccess', { username: updatedUser.username }));
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      console.error('Brand linking error:', error);
      // Если операция выполнена (статус 200-299), но есть ошибка в ответе - все равно закрываем модалку
      // и обновляем данные, так как привязка могла произойти
      if ((error?.response?.status ?? 0) >= 200 && (error?.response?.status ?? 0) < 300) {
        queryClient.invalidateQueries({ queryKey: ['admin-users'] });
        setSelectedUserIdForBrand(null);
        setSelectedBrandId(null);
        showActionSuccess(t('adminUsers.feedback.brandLinkSuccessGeneric'));
      } else {
        showActionError(error, 'adminUsers.feedback.brandLinkError');
      }
    },
  });

  // Отвязка от бренда
  const unlinkBrandMutation = useMutation({
    mutationFn: (userId: number) => adminAPI.unlinkUserFromBrand(userId),
    onSuccess: (updatedUser) => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      showActionSuccess(t('adminUsers.feedback.brandUnlinkSuccess', { username: updatedUser.username }));
    },
    onError: (error: AxiosError<{ detail: unknown }>) =>
      showActionError(error, 'adminUsers.feedback.brandUnlinkError'),
  });

  const achievementOverviewQuery = useQuery({
    queryKey: ['admin-user-achievements', selectedAchievementUser?.id],
    queryFn: () => adminAPI.getUserAchievements(selectedAchievementUser!.id),
    enabled: selectedAchievementUser !== null,
  });

  const grantAchievementMutation = useMutation({
    mutationFn: ({ userId, code, reason }: { userId: number; code: string; reason: string }) =>
      adminAPI.grantUserAchievement(userId, code, reason),
    onSuccess: (overview, variables) => {
      queryClient.setQueryData(['admin-user-achievements', variables.userId], overview);
      setSelectedAchievementCode('');
      setAchievementReason('');
      showActionSuccess(t('adminUsers.feedback.achievementGrantSuccess'));
    },
    onError: (error: AxiosError<{ detail: unknown }>) =>
      showActionError(error, 'adminUsers.feedback.achievementGrantError'),
  });

  const revokeAchievementMutation = useMutation({
    mutationFn: ({ userId, code, reason }: { userId: number; code: string; reason: string }) =>
      adminAPI.revokeUserAchievement(userId, code, reason),
    onSuccess: (overview, variables) => {
      queryClient.setQueryData(['admin-user-achievements', variables.userId], overview);
      setRevokeAchievementCode(null);
      setAchievementReason('');
      showActionSuccess(t('adminUsers.feedback.achievementRevokeSuccess'));
    },
    onError: (error: AxiosError<{ detail: unknown }>) =>
      showActionError(error, 'adminUsers.feedback.achievementRevokeError'),
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
  const [confirmErase, setConfirmErase] = useState<{ userId: number; username: string } | null>(null);
  const { data: erasePreview } = useQuery({
    queryKey: ['admin-user-deletion-preview', confirmErase?.userId],
    queryFn: () => adminAPI.previewUserDeletion(confirmErase!.userId),
    enabled: !!confirmErase,
  });
  const [confirmPromote, setConfirmPromote] = useState<{ userId: number; username: string } | null>(null);
  const [confirmDemote, setConfirmDemote] = useState<{ userId: number; username: string } | null>(null);
  const [confirmUnlink, setConfirmUnlink] = useState<{ userId: number; username: string; brandName: string } | null>(null);

  const usersList = usersPage?.items ?? [];
  const total = usersPage?.total ?? 0;
  const totalPages = usersPage?.total_pages ?? 0;
  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, total);
  const dateFormatter = useMemo(
    () => new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium' }),
    [i18n.language],
  );
  const pageNumbers = useMemo(() => {
    if (totalPages <= 5) {
      return Array.from({ length: totalPages }, (_, index) => index + 1);
    }
    const start = Math.min(Math.max(page - 2, 1), totalPages - 4);
    return Array.from({ length: 5 }, (_, index) => start + index);
  }, [page, totalPages]);

  useEffect(() => {
    if (totalPages > 0 && page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  if (isLoading) {
    return <div className="py-12 text-center text-gray-400">{t('adminUsers.loading')}</div>;
  }

  const actionButtonClass =
    'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-gray-400 transition hover:border-white/20 hover:bg-white/[0.09] hover:text-white disabled:cursor-not-allowed disabled:opacity-40';

  return (
    <div className="space-y-4">
      <header className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <h2 className="text-xl font-semibold text-white">{t('adminUsers.title')}</h2>
            <p className="mt-1 text-sm text-gray-500">
              {t('adminUsers.total')}: <span className="font-medium text-gray-300">{total}</span>
            </p>
          </div>

          <div className="flex flex-1 flex-col gap-2 sm:flex-row xl:max-w-3xl xl:justify-end">
            <label className="relative min-w-0 flex-1 xl:max-w-sm">
              <span className="sr-only">{t('adminUsers.searchLabel')}</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t('adminUsers.searchPlaceholder')}
                className="h-10 w-full rounded-lg border border-white/10 bg-black/15 pl-9 pr-3 text-sm text-white outline-none transition placeholder:text-gray-600 focus:border-purple-400/40 focus:ring-2 focus:ring-purple-400/10"
              />
            </label>

            <label className="flex h-10 items-center gap-2 rounded-lg border border-white/10 bg-black/15 px-3 text-xs text-gray-500">
              <span>{t('adminUsers.pageSize')}</span>
              <select
                value={pageSize}
                onChange={(event) => setPageSize(Number(event.target.value))}
                className="bg-transparent text-sm text-gray-200 outline-none"
              >
                {[20, 50, 100].map((value) => (
                  <option key={value} value={value} className="bg-gray-900">
                    {value}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/5 pt-3">
          {[
            { value: undefined, label: t('adminUsers.filterAll') },
            { value: 'user', label: t('adminUsers.filterUsers') },
            { value: 'admin', label: t('adminUsers.filterAdmins') },
          ].map((filter) => (
            <button
              key={filter.value ?? 'all'}
              type="button"
              onClick={() => setRoleFilter(filter.value)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                roleFilter === filter.value
                  ? 'bg-purple-500/20 text-purple-200 ring-1 ring-inset ring-purple-400/25'
                  : 'bg-white/[0.04] text-gray-400 hover:bg-white/[0.08] hover:text-gray-200'
              }`}
            >
              {filter.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setShowOnlyWithBrand((current) => !current)}
            aria-pressed={showOnlyWithBrand}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              showOnlyWithBrand
                ? 'bg-purple-500/20 text-purple-200 ring-1 ring-inset ring-purple-400/25'
                : 'bg-white/[0.04] text-gray-400 hover:bg-white/[0.08] hover:text-gray-200'
            }`}
          >
            <Factory className="h-3.5 w-3.5" />
            {t('adminUsers.filterWithBrand')}
          </button>
          {isFetching && (
            <span className="ml-auto text-xs text-gray-600">{t('adminUsers.updating')}</span>
          )}
        </div>
      </header>

      {usersList.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/10 py-12 text-center text-gray-500">
          <Users className="mx-auto mb-3 h-10 w-10 opacity-40" />
          <p>{t('adminUsers.empty')}</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-white/10 bg-[#121225]/55" aria-busy={isFetching}>
          <div className="divide-y divide-white/[0.06]">
            {usersList.map((user) => {
              const isAdmin = user.role === 'admin';
              const roleLabel = isAdmin ? t('adminUsers.roleAdmin') : t('adminUsers.roleUser');
              const isComplimentaryPro = Boolean(user.subscription?.is_comp);

              return (
                <article
                  key={user.id}
                  className={`grid gap-3 px-3 py-2.5 transition hover:bg-white/[0.035] lg:grid-cols-[minmax(190px,1fr)_minmax(230px,1.2fr)_minmax(180px,1fr)_auto] lg:items-center ${
                    user.active ? '' : 'bg-rose-500/[0.025]'
                  }`}
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <span
                      className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg border ${
                        isAdmin
                          ? 'border-amber-400/20 bg-amber-400/10 text-amber-300'
                          : 'border-white/10 bg-white/[0.04] text-gray-400'
                      }`}
                      title={roleLabel}
                      aria-label={roleLabel}
                    >
                      {isAdmin ? <Shield className="h-4 w-4" /> : <UserRound className="h-4 w-4" />}
                    </span>
                    <div className="min-w-0">
                      <div className="flex min-w-0 items-center gap-2">
                        <h3 className="truncate text-sm font-semibold text-gray-100">{user.username}</h3>
                        <span
                          className={`h-1.5 w-1.5 shrink-0 rounded-full ${user.active ? 'bg-emerald-400' : 'bg-rose-400'}`}
                          title={user.active ? t('adminUsers.active') : t('adminUsers.deactivated')}
                          aria-label={user.active ? t('adminUsers.active') : t('adminUsers.deactivated')}
                        />
                        {!user.active && (
                          <span className="shrink-0 text-[10px] font-medium text-rose-300">
                            {t('adminUsers.deactivated')}
                          </span>
                        )}
                      </div>
                      {user.full_name && (
                        <p className="truncate text-[11px] text-gray-600">{user.full_name}</p>
                      )}
                    </div>
                  </div>

                  <div className="min-w-0 text-xs">
                    <p className="truncate text-gray-300" title={user.email}>{user.email}</p>
                    <p className="mt-0.5 text-[10px] text-gray-600">
                      {t('adminUsers.created')} {dateFormatter.format(new Date(user.created_at))}
                    </p>
                  </div>

                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    {user.brand_id && (
                      <span
                        className="inline-flex max-w-full items-center gap-1 rounded-md border border-purple-400/15 bg-purple-400/[0.08] px-1.5 py-1 text-[10px] text-purple-200"
                        title={`${t('adminUsers.representative')}: ${user.brand_name || `#${user.brand_id}`}`}
                      >
                        <Factory className="h-3 w-3 shrink-0" />
                        <span className="truncate">{user.brand_name || `#${user.brand_id}`}</span>
                      </span>
                    )}
                    {isComplimentaryPro && (
                      <span className="rounded-md border border-cyan-400/15 bg-cyan-400/[0.08] px-1.5 py-1 text-[10px] font-medium text-cyan-200">
                        {t('adminUsers.proOn')}
                      </span>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-1 lg:justify-end">
                    <button
                      type="button"
                      onClick={() => setConfirmErase({ userId: user.id, username: user.username })}
                      disabled={user.role === 'admin' || eraseMutation.isPending}
                      className={`${actionButtonClass} hover:border-rose-400/25 hover:text-rose-300 disabled:opacity-40`}
                      title={t('adminUsers.eraseTitle')}
                      aria-label={t('adminUsers.eraseTitle')}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => user.active
                        ? setConfirmDeactivate({ userId: user.id, username: user.username })
                        : setConfirmActivate({ userId: user.id, username: user.username })}
                      disabled={activateMutation.isPending || deactivateMutation.isPending}
                      className={`${actionButtonClass} ${user.active ? 'hover:border-rose-400/25 hover:text-rose-300' : 'text-emerald-400 hover:border-emerald-400/25 hover:text-emerald-300'}`}
                      title={user.active ? t('adminUsers.deactivateTitle') : t('adminUsers.activateTitle')}
                      aria-label={user.active ? t('adminUsers.deactivateTitle') : t('adminUsers.activateTitle')}
                    >
                      {user.active ? <CircleOff className="h-4 w-4" /> : <CheckCircle className="h-4 w-4" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => isAdmin
                        ? setConfirmDemote({ userId: user.id, username: user.username })
                        : setConfirmPromote({ userId: user.id, username: user.username })}
                      disabled={promoteMutation.isPending || demoteMutation.isPending}
                      className={`${actionButtonClass} ${isAdmin ? 'text-amber-300' : ''}`}
                      title={isAdmin ? t('adminUsers.demoteTitle') : t('adminUsers.promoteTitle')}
                      aria-label={isAdmin ? t('adminUsers.demoteTitle') : t('adminUsers.promoteTitle')}
                    >
                      <Shield className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedAchievementUser({ id: user.id, username: user.username });
                        setSelectedAchievementCode('');
                        setAchievementReason('');
                        setRevokeAchievementCode(null);
                      }}
                      className={actionButtonClass}
                      title={t('adminUsers.manageAchievementsTitle')}
                      aria-label={t('adminUsers.manageAchievementsTitle')}
                    >
                      <Award className="h-4 w-4" />
                    </button>
                    {!isAdmin && (
                      <button
                        type="button"
                        onClick={() => proAccessMutation.mutate({ userId: user.id, grant: !isComplimentaryPro })}
                        disabled={proAccessMutation.isPending}
                        aria-pressed={isComplimentaryPro}
                        className={`${actionButtonClass} ${isComplimentaryPro ? 'border-cyan-400/20 bg-cyan-400/10 text-cyan-300' : ''}`}
                        title={t('adminUsers.proAccessTitle')}
                        aria-label={t('adminUsers.proAccessTitle')}
                      >
                        <Calculator className="h-4 w-4" />
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        if (user.brand_id) {
                          setConfirmUnlink({
                            userId: user.id,
                            username: user.username,
                            brandName: user.brand_name || `#${user.brand_id}`,
                          });
                        } else {
                          setSelectedUserIdForBrand(user.id);
                          setSelectedBrandId(null);
                        }
                      }}
                      disabled={unlinkBrandMutation.isPending}
                      className={`${actionButtonClass} ${user.brand_id ? 'text-orange-300' : ''}`}
                      title={user.brand_id ? t('adminUsers.unlinkBrandTitle') : t('adminUsers.linkBrandTitle')}
                      aria-label={user.brand_id ? t('adminUsers.unlinkBrandTitle') : t('adminUsers.linkBrandTitle')}
                    >
                      {user.brand_id ? <Unlink className="h-4 w-4" /> : <Link2 className="h-4 w-4" />}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      )}

      <footer className="flex flex-col gap-3 rounded-xl border border-white/10 bg-white/[0.025] px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-gray-500">
          {t('adminUsers.range', { start: rangeStart, end: rangeEnd, total })}
        </p>
        {totalPages > 1 && (
          <nav className="flex flex-wrap items-center gap-1" aria-label={t('adminUsers.paginationLabel')}>
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1 || isFetching}
              className={actionButtonClass}
              title={t('adminUsers.previous')}
              aria-label={t('adminUsers.previous')}
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            {pageNumbers.map((pageNumber) => (
              <button
                key={pageNumber}
                type="button"
                onClick={() => setPage(pageNumber)}
                disabled={isFetching}
                aria-current={pageNumber === page ? 'page' : undefined}
                className={`h-8 min-w-8 rounded-lg px-2 text-xs font-medium transition ${
                  pageNumber === page
                    ? 'bg-purple-500/20 text-purple-100 ring-1 ring-inset ring-purple-400/25'
                    : 'text-gray-500 hover:bg-white/[0.07] hover:text-gray-200'
                }`}
              >
                {pageNumber}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              disabled={page >= totalPages || isFetching}
              className={actionButtonClass}
              title={t('adminUsers.next')}
              aria-label={t('adminUsers.next')}
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </nav>
        )}
      </footer>
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
        isOpen={!!confirmErase}
        onClose={() => setConfirmErase(null)}
        onConfirm={() => {
          if (confirmErase) {
            eraseMutation.mutate(confirmErase.userId);
            setConfirmErase(null);
          }
        }}
        title={t('adminUsers.eraseTitle')}
        message={t('adminUsers.confirmErase', {
          username: confirmErase?.username,
          presets: erasePreview?.presets_count ?? '…',
          spools: erasePreview?.spools_count ?? '…',
          reviews: erasePreview?.reviews_count ?? '…',
        })}
        confirmText={t('adminUsers.erase')}
        isLoading={eraseMutation.isPending}
        variant="danger"
        icon={<Trash2 className="w-5 h-5" />}
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

      {selectedAchievementUser && (
        <ModalOverlay onClose={() => setSelectedAchievementUser(null)}>
          <div
            className="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/10 bg-gray-900 p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-xl font-bold text-white">
              {t('adminUsers.manageAchievementsTitle')}
            </h3>
            <p className="mt-1 text-sm text-gray-400">
              {t('adminUsers.manageAchievementsDescription', {
                username: selectedAchievementUser.username,
              })}
            </p>

            <section className="mt-5">
              <h4 className="text-sm font-semibold text-white">
                {t('adminUsers.earnedAchievements')}
              </h4>
              {achievementOverviewQuery.isLoading ? (
                <p className="mt-3 text-sm text-gray-400">{t('common.loading')}</p>
              ) : (
                <div className="mt-3 space-y-2">
                  {(achievementOverviewQuery.data?.achievements ?? [])
                    .filter((achievement) => achievement.revoked_at === null)
                    .map((achievement) => {
                      const code = achievement.code;
                      const knownCode = isAchievementCode(code) ? code : null;
                      return (
                        <div
                          key={code}
                          className="flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.04] p-3"
                        >
                          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-black/20">
                            {knownCode ? <AchievementBadge code={knownCode} /> : <Award className="h-5 w-5" />}
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="font-medium text-white">
                              {knownCode ? t(ACHIEVEMENT_CONFIG[knownCode].labelKey) : code}
                            </p>
                            <p className="text-xs text-gray-400">
                              {t(`adminUsers.achievementSource.${achievement.source}`)}
                            </p>
                            {achievement.award_reason && (
                              <p className="mt-1 text-xs text-gray-300">{achievement.award_reason}</p>
                            )}
                          </div>
                          {(achievement.source === 'manual' || achievement.source === 'migration') && (
                            <button
                              type="button"
                              onClick={() => {
                                setRevokeAchievementCode(knownCode);
                                setAchievementReason('');
                              }}
                              disabled={!knownCode}
                              className="rounded-lg border border-rose-400/20 px-2.5 py-1.5 text-xs text-rose-300 hover:bg-rose-400/10 disabled:opacity-40"
                            >
                              {t('adminUsers.revokeAchievement')}
                            </button>
                          )}
                        </div>
                      );
                    })}
                  {(achievementOverviewQuery.data?.achievements ?? []).every(
                    (achievement) => achievement.revoked_at !== null,
                  ) && (
                    <p className="rounded-xl border border-white/10 p-3 text-sm text-gray-400">
                      {t('adminUsers.noAchievements')}
                    </p>
                  )}
                </div>
              )}
            </section>

            <section className="mt-6 border-t border-white/10 pt-5">
              {revokeAchievementCode ? (
                <>
                  <h4 className="text-sm font-semibold text-rose-200">
                    {t('adminUsers.revokeAchievementTitle', {
                      achievement: t(ACHIEVEMENT_CONFIG[revokeAchievementCode].labelKey),
                    })}
                  </h4>
                  <p className="mt-1 text-xs leading-5 text-gray-400">
                    {t('adminUsers.revokeAchievementDescription')}
                  </p>
                </>
              ) : (
                <>
                  <h4 className="text-sm font-semibold text-white">
                    {t('adminUsers.grantAchievementTitle')}
                  </h4>
                  <p className="mt-1 text-xs leading-5 text-gray-400">
                    {t('adminUsers.grantAchievementDescription')}
                  </p>
                  <select
                    value={selectedAchievementCode}
                    onChange={(event) => setSelectedAchievementCode(event.target.value as AchievementCode | '')}
                    className="mt-3 w-full rounded-lg border border-white/10 bg-gray-800 px-3 py-2 text-sm text-white"
                  >
                    <option value="">{t('adminUsers.selectAchievement')}</option>
                    {(achievementOverviewQuery.data?.manual_awardable_codes ?? [])
                      .filter((code) => isAchievementCode(code))
                      .filter((code) => !(achievementOverviewQuery.data?.achievements ?? []).some(
                        (achievement) => achievement.code === code,
                      ))
                      .map((code) => (
                        <option key={code} value={code}>
                          {t(ACHIEVEMENT_CONFIG[code].labelKey)}
                        </option>
                      ))}
                  </select>
                </>
              )}
              <textarea
                value={achievementReason}
                onChange={(event) => setAchievementReason(event.target.value)}
                placeholder={t('adminUsers.achievementReasonPlaceholder')}
                maxLength={1000}
                className="mt-3 min-h-24 w-full rounded-lg border border-white/10 bg-gray-800 px-3 py-2 text-sm text-white placeholder:text-gray-500"
              />
            </section>

            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => {
                  if (revokeAchievementCode) {
                    setRevokeAchievementCode(null);
                    setAchievementReason('');
                  } else {
                    setSelectedAchievementUser(null);
                  }
                }}
                className="rounded-lg bg-white/5 px-4 py-2 text-white transition-all hover:bg-white/10"
              >
                {t('adminUsers.cancel')}
              </button>
              <button
                onClick={() => {
                  if (revokeAchievementCode) {
                    revokeAchievementMutation.mutate({
                      userId: selectedAchievementUser.id,
                      code: revokeAchievementCode,
                      reason: achievementReason.trim(),
                    });
                  } else if (selectedAchievementCode) {
                    grantAchievementMutation.mutate({
                      userId: selectedAchievementUser.id,
                      code: selectedAchievementCode,
                      reason: achievementReason.trim(),
                    });
                  }
                }}
                disabled={
                  achievementReason.trim().length < 3
                  || (!revokeAchievementCode && !selectedAchievementCode)
                  || grantAchievementMutation.isPending
                  || revokeAchievementMutation.isPending
                }
                className={`rounded-lg px-4 py-2 text-white transition-all disabled:opacity-40 ${
                  revokeAchievementCode
                    ? 'bg-rose-600 hover:bg-rose-700'
                    : 'bg-purple-600 hover:bg-purple-700'
                }`}
              >
                {revokeAchievementCode
                  ? t('adminUsers.revokeAchievement')
                  : t('adminUsers.grantAchievement')}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}


