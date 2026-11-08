import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, Loader2, Sparkles } from 'lucide-react';

import { subscriptionAPI } from '../api/client';
import type { User } from '../types/api';
import { apiErrorDetail } from '../utils/apiErrorDetail';
import { translateApiError } from '../utils/translateApiError';

interface WorkshopInterestCardProps {
  user: User;
  onUserUpdate: () => void | Promise<void>;
}

export function WorkshopInterestCard({ user, onUserUpdate }: WorkshopInterestCardProps) {
  const { t } = useTranslation();
  const [justJoined, setJustJoined] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const subscription = user.subscription;
  const now = Date.now();
  const trialEnd = subscription?.trial_ends_at
    ? new Date(subscription.trial_ends_at).getTime()
    : null;
  const periodEnd = subscription?.current_period_end
    ? new Date(subscription.current_period_end).getTime()
    : null;
  const isInterested = subscription?.status === 'interested';
  const isAdmin = user.role === 'admin';
  const hasAccess =
    Boolean(subscription?.is_comp) ||
    (subscription?.status === 'active' && (periodEnd === null || periodEnd > now)) ||
    (subscription?.status === 'trialing' && (trialEnd === null || trialEnd > now));
  const hasPendingBilling = subscription?.status === 'past_due';
  const showJoined = isInterested || justJoined;
  const joinedAt = subscription?.interested_at
    ? new Date(subscription.interested_at).toLocaleDateString()
    : null;

  const joinMutation = useMutation({
    mutationFn: () => subscriptionAPI.joinWorkshopInterest(),
    onSuccess: async () => {
      setError(null);
      setJustJoined(true);
      await onUserUpdate();
    },
    onError: (requestError: unknown) => {
      setError(
        translateApiError(
          t,
          apiErrorDetail(requestError),
          t('settings.workshopInterest.error'),
        ),
      );
    },
  });

  const leaveMutation = useMutation({
    mutationFn: () => subscriptionAPI.leaveWorkshopInterest(),
    onSuccess: async () => {
      setError(null);
      setJustJoined(false);
      await onUserUpdate();
    },
    onError: (requestError: unknown) => {
      setError(
        translateApiError(
          t,
          apiErrorDetail(requestError),
          t('settings.workshopInterest.error'),
        ),
      );
    },
  });

  const busy = joinMutation.isPending || leaveMutation.isPending;

  return (
    <section className="rounded-[1.75rem] border border-white/10 bg-slate-950/55 p-5 shadow-2xl shadow-black/20 md:p-6">
      <div className="flex items-start gap-3">
        <div className="shrink-0 rounded-xl bg-cyan-400/10 p-2 text-cyan-300">
          <Sparkles className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <h3 className="text-lg font-bold text-white">
            {t('settings.workshopInterest.title')}
          </h3>
          <p className="mt-0.5 text-xs text-gray-400">
            {t('settings.workshopInterest.subtitle')}
          </p>
        </div>
      </div>

      <div className="mt-4 space-y-3 text-sm leading-6 text-gray-300">
        <p>{t('settings.workshopInterest.p1')}</p>
        <p>{t('settings.workshopInterest.p2')}</p>
        <p>{t('settings.workshopInterest.p3')}</p>
      </div>

      <div aria-live="polite" className="mt-4 space-y-3">
        {error && (
          <p role="alert" className="text-sm text-red-300">
            {error}
          </p>
        )}
        {justJoined && (
          <div className="flex items-start gap-2 rounded-xl border border-green-400/20 bg-green-400/10 p-3 text-sm text-green-100">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{t('settings.workshopInterest.success')}</span>
          </div>
        )}
      </div>

      <div className="mt-4">
        {isAdmin ? (
          <p className="text-sm text-gray-400">
            {t('settings.workshopInterest.adminNote')}
          </p>
        ) : hasAccess ? (
          <p className="text-sm text-cyan-200">
            {t('settings.workshopInterest.alreadyActive')}
          </p>
        ) : hasPendingBilling ? (
          <p className="text-sm text-amber-200">
            {t('settings.workshopInterest.pendingBilling')}
          </p>
        ) : showJoined ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <p className="inline-flex items-center gap-2 text-sm text-cyan-200">
              <CheckCircle2 className="h-4 w-4" />
              {joinedAt
                ? t('settings.workshopInterest.joinedAt', { date: joinedAt })
                : t('settings.workshopInterest.joined')}
            </p>
            <button
              type="button"
              onClick={() => leaveMutation.mutate()}
              disabled={busy}
              className="text-xs text-gray-400 underline-offset-2 hover:text-white hover:underline disabled:opacity-50"
            >
              {leaveMutation.isPending
                ? t('settings.workshopInterest.leaving')
                : t('settings.workshopInterest.leave')}
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => joinMutation.mutate()}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-xl border border-cyan-400/30 bg-cyan-400/10 px-4 py-2.5 text-sm font-medium text-cyan-50 transition hover:bg-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {joinMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            {joinMutation.isPending
              ? t('settings.workshopInterest.loading')
              : t('settings.workshopInterest.join')}
          </button>
        )}
      </div>
    </section>
  );
}
