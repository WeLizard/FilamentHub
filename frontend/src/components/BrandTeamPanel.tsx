import { useState } from 'react';
import type { AxiosError } from 'axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Check,
  Copy,
  Crown,
  Link2,
  Loader2,
  MailPlus,
  Shield,
  UserMinus,
  Users,
  X,
} from 'lucide-react';
import { brandTeamAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { translateApiError } from '../utils/translateApiError';
import { ConfirmModal } from './ConfirmModal';
import { toast } from './Toast';
import type { BrandTeamRole } from '../types/api';

interface BrandTeamPanelProps {
  brandId: number;
}

interface PendingMemberAction {
  kind: 'remove' | 'transfer';
  membershipId: number;
  username: string;
}

const statusTone: Record<string, string> = {
  pending: 'border-amber-400/25 bg-amber-400/10 text-amber-200',
  sent: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-200',
  failed: 'border-red-400/25 bg-red-400/10 text-red-200',
  accepted: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-200',
  expired: 'border-white/10 bg-white/5 text-gray-400',
  revoked: 'border-white/10 bg-white/5 text-gray-500',
};

function apiErrorDetail(error: unknown): unknown {
  return (error as AxiosError<{ detail?: unknown }>).response?.data?.detail;
}

export function BrandTeamPanel({ brandId }: BrandTeamPanelProps) {
  const { t } = useTranslation();
  const { refreshUser } = useAuth();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<BrandTeamRole>('editor');
  const [allBrands, setAllBrands] = useState(false);
  const [pendingMemberAction, setPendingMemberAction] = useState<PendingMemberAction | null>(null);

  const query = useQuery({
    queryKey: ['brand-team', brandId],
    queryFn: () => brandTeamAPI.get(brandId),
  });

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['brand-team', brandId] }),
      queryClient.invalidateQueries({ queryKey: ['accessible-brands'] }),
      refreshUser(),
    ]);
  };

  const inviteMutation = useMutation({
    mutationFn: (sendEmail: boolean) => brandTeamAPI.invite(brandId, {
      email,
      role,
      all_brands: role === 'owner' || allBrands,
      send_email: sendEmail,
    }),
    onSuccess: async (invite, sendEmail) => {
      if (!sendEmail) {
        await navigator.clipboard.writeText(invite.invite_url);
      }
      setEmail('');
      await refresh();
      toast.success(t(sendEmail ? 'brandTeam.inviteSent' : 'brandTeam.linkCopied'));
    },
    onError: (error) => toast.error(
      translateApiError(t, apiErrorDetail(error), t('brandTeam.actionError')),
    ),
  });

  const actionMutation = useMutation({
    mutationFn: async (action: () => Promise<void>) => action(),
    onSuccess: async () => {
      setPendingMemberAction(null);
      await refresh();
    },
    onError: (error) => toast.error(
      translateApiError(t, apiErrorDetail(error), t('brandTeam.actionError')),
    ),
  });

  const confirmMemberAction = () => {
    if (!pendingMemberAction) return;
    actionMutation.mutate(() => (
      pendingMemberAction.kind === 'transfer'
        ? brandTeamAPI.transferOwnership(brandId, pendingMemberAction.membershipId)
        : brandTeamAPI.removeMember(brandId, pendingMemberAction.membershipId)
    ));
  };

  if (query.isLoading) {
    return <div className="flex min-h-56 items-center justify-center text-cyan-200"><Loader2 className="h-6 w-6 animate-spin" /></div>;
  }
  if (query.isError || !query.data) {
    return <div className="rounded-2xl border border-red-400/20 bg-red-400/10 p-5 text-sm text-red-200">{t('brandTeam.loadError')}</div>;
  }

  const workspace = query.data;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 rounded-2xl border border-cyan-300/15 bg-slate-950/35 p-5 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-cyan-300/20 bg-cyan-300/10 text-cyan-200">
            <Users className="h-5 w-5" />
          </span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200/60">{t('brandTeam.organization')}</p>
            <h3 className="text-xl font-semibold text-white">{workspace.organization_name}</h3>
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-300">
          {workspace.current_role === 'owner' ? <Crown className="h-4 w-4 text-amber-300" /> : <Shield className="h-4 w-4 text-cyan-300" />}
          {t(`brandTeam.roles.${workspace.current_role}`)}
        </div>
      </div>

      {workspace.can_manage_team && (
        <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
          <div className="mb-4 flex items-center gap-2">
            <MailPlus className="h-5 w-5 text-violet-300" />
            <h4 className="font-semibold text-white">{t('brandTeam.inviteTitle')}</h4>
          </div>
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_160px_auto]">
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder={t('brandTeam.emailPlaceholder')}
              className="min-w-0 rounded-xl border border-white/15 bg-slate-950/45 px-4 py-3 text-white outline-none transition placeholder:text-gray-500 focus:border-cyan-300/60"
            />
            <select
              value={role}
              onChange={(event) => setRole(event.target.value as BrandTeamRole)}
              className="rounded-xl border border-white/15 bg-slate-950 px-3 py-3 text-white outline-none focus:border-cyan-300/60"
            >
              <option value="editor">{t('brandTeam.roles.editor')}</option>
              <option value="owner">{t('brandTeam.roles.owner')}</option>
            </select>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => inviteMutation.mutate(true)}
                disabled={!email.trim() || inviteMutation.isPending}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-cyan-400 px-4 py-3 font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:opacity-40"
              >
                <MailPlus className="h-4 w-4" /> {t('brandTeam.send')}
              </button>
              <button
                type="button"
                onClick={() => inviteMutation.mutate(false)}
                disabled={!email.trim() || inviteMutation.isPending}
                title={t('brandTeam.copyLink')}
                className="rounded-xl border border-white/15 bg-white/5 px-3 text-gray-200 transition hover:bg-white/10 disabled:opacity-40"
              >
                <Link2 className="h-4 w-4" />
              </button>
            </div>
          </div>
          <label className="mt-3 inline-flex items-center gap-2 text-sm text-gray-400">
            <input
              type="checkbox"
              checked={role === 'owner' || allBrands}
              disabled={role === 'owner'}
              onChange={(event) => setAllBrands(event.target.checked)}
              className="h-4 w-4 rounded border-white/20 bg-white/10 text-cyan-400"
            />
            {t('brandTeam.allBrands')}
          </label>
          <p className="mt-2 text-xs leading-5 text-gray-500">{t('brandTeam.exactEmailHint')}</p>
        </section>
      )}

      <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
        <h4 className="mb-4 font-semibold text-white">{t('brandTeam.membersTitle')}</h4>
        <div className="divide-y divide-white/10">
          {workspace.members.map((member) => (
            <div key={member.membership_id} className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 md:flex-row md:items-center">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate font-medium text-white">{member.username}</p>
                  {member.is_current_user && <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-gray-300">{t('brandTeam.you')}</span>}
                </div>
                <p className="truncate text-sm text-gray-500">{member.email}</p>
              </div>
              <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-gray-200">
                {member.role === 'owner' && <Crown className="h-3.5 w-3.5 text-amber-300" />}
                {t(`brandTeam.roles.${member.role}`)}
              </span>
              {workspace.can_manage_team && !member.is_current_user && (
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={member.role}
                    onChange={(event) => {
                      const nextRole = event.target.value as BrandTeamRole;
                      actionMutation.mutate(() => brandTeamAPI.updateMember(brandId, member.membership_id, {
                        role: nextRole,
                        all_brands: nextRole === 'owner' || member.all_brands,
                        brand_ids: nextRole === 'owner' || member.all_brands ? [] : [brandId],
                      }));
                    }}
                    className="rounded-lg border border-white/10 bg-slate-950 px-2 py-2 text-xs text-gray-200"
                    aria-label={t('brandTeam.changeRole')}
                  >
                    <option value="editor">{t('brandTeam.roles.editor')}</option>
                    <option value="owner">{t('brandTeam.roles.owner')}</option>
                  </select>
                  {member.role === 'editor' && (
                    <select
                      value={member.all_brands ? 'all' : 'current'}
                      onChange={(event) => actionMutation.mutate(() => brandTeamAPI.updateMember(brandId, member.membership_id, {
                        role: 'editor',
                        all_brands: event.target.value === 'all',
                        brand_ids: event.target.value === 'all' ? [] : [brandId],
                      }))}
                      className="rounded-lg border border-white/10 bg-slate-950 px-2 py-2 text-xs text-gray-200"
                      aria-label={t('brandTeam.changeScope')}
                    >
                      <option value="current">{t('brandTeam.currentBrand')}</option>
                      <option value="all">{t('brandTeam.allBrandsShort')}</option>
                    </select>
                  )}
                  {member.role !== 'owner' && (
                    <button
                      type="button"
                      onClick={() => setPendingMemberAction({
                        kind: 'transfer',
                        membershipId: member.membership_id,
                        username: member.username,
                      })}
                      className="rounded-lg border border-amber-300/20 bg-amber-300/10 px-3 py-2 text-xs text-amber-100 hover:bg-amber-300/15"
                    >
                      {t('brandTeam.transfer')}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setPendingMemberAction({
                      kind: 'remove',
                      membershipId: member.membership_id,
                      username: member.username,
                    })}
                    title={t('brandTeam.remove')}
                    className="rounded-lg border border-red-300/15 bg-red-300/5 p-2 text-red-200 hover:bg-red-300/10"
                  >
                    <UserMinus className="h-4 w-4" />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {workspace.can_manage_team && workspace.pending_join_requests.length > 0 && (
        <section className="rounded-2xl border border-emerald-300/15 bg-emerald-300/[0.04] p-5">
          <h4 className="mb-4 font-semibold text-white">{t('brandTeam.requestsTitle')}</h4>
          <div className="space-y-3">
            {workspace.pending_join_requests.map((request) => (
              <div key={request.id} className="flex flex-col gap-3 rounded-xl border border-white/10 bg-slate-950/30 p-4 md:flex-row md:items-center">
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-white">{request.username}</p>
                  <p className="truncate text-sm text-gray-500">{request.email}</p>
                  {request.message && <p className="mt-2 text-sm text-gray-300">{request.message}</p>}
                </div>
                <div className="flex gap-2">
                  <button type="button" onClick={() => actionMutation.mutate(() => brandTeamAPI.decideJoinRequest(brandId, request.id, 'approved'))} className="rounded-lg bg-emerald-400/15 p-2 text-emerald-200 hover:bg-emerald-400/25" title={t('brandTeam.approve')}><Check className="h-4 w-4" /></button>
                  <button type="button" onClick={() => actionMutation.mutate(() => brandTeamAPI.decideJoinRequest(brandId, request.id, 'rejected'))} className="rounded-lg bg-red-400/10 p-2 text-red-200 hover:bg-red-400/20" title={t('brandTeam.reject')}><X className="h-4 w-4" /></button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {workspace.can_manage_team && workspace.pending_invites.length > 0 && (
        <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
          <h4 className="mb-4 font-semibold text-white">{t('brandTeam.invitesTitle')}</h4>
          <div className="space-y-2">
            {workspace.pending_invites.map((invite) => (
              <div key={invite.id} className="flex flex-col gap-3 rounded-xl border border-white/10 bg-slate-950/30 px-4 py-3 md:flex-row md:items-center">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-white">{invite.email}</p>
                  <p className="text-xs text-gray-500">{t(`brandTeam.roles.${invite.role}`)}</p>
                </div>
                <span className={`w-fit rounded-full border px-2.5 py-1 text-[11px] ${statusTone[invite.status] ?? statusTone.pending}`}>{t(`brandTeam.status.${invite.status}`)}</span>
                {['pending', 'sent', 'failed'].includes(invite.status) && (
                  <div className="flex gap-2">
                    <button type="button" onClick={async () => { await navigator.clipboard.writeText(invite.invite_url); toast.success(t('brandTeam.linkCopied')); }} className="rounded-lg border border-white/10 p-2 text-gray-300 hover:bg-white/10" title={t('brandTeam.copyLink')}><Copy className="h-4 w-4" /></button>
                    <button type="button" onClick={() => actionMutation.mutate(() => brandTeamAPI.revokeInvite(brandId, invite.id))} className="rounded-lg border border-red-300/10 p-2 text-red-200 hover:bg-red-300/10" title={t('brandTeam.revoke')}><X className="h-4 w-4" /></button>
                  </div>
                )}
                {invite.status === 'accepted' && <Check className="h-4 w-4 text-emerald-300" />}
              </div>
            ))}
          </div>
        </section>
      )}

      <ConfirmModal
        isOpen={pendingMemberAction !== null}
        onClose={() => !actionMutation.isPending && setPendingMemberAction(null)}
        onConfirm={confirmMemberAction}
        isLoading={actionMutation.isPending}
        variant={pendingMemberAction?.kind === 'remove' ? 'danger' : 'warning'}
        title={t(`brandTeam.confirm.${pendingMemberAction?.kind ?? 'remove'}.title`)}
        message={t(`brandTeam.confirm.${pendingMemberAction?.kind ?? 'remove'}.message`, {
          username: pendingMemberAction?.username ?? '',
        })}
        confirmText={t(`brandTeam.confirm.${pendingMemberAction?.kind ?? 'remove'}.action`)}
      />
    </div>
  );
}
