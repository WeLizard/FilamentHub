import { useTranslation } from 'react-i18next';
import { Sparkles, Clock } from 'lucide-react';
import type { User } from '../types/api';

/** User-facing subscription status: plan, trial countdown, and (coming-soon) upgrade CTA. */
export function SubscriptionCard({ user }: { user: User }) {
  const { t } = useTranslation();
  const sub = user.subscription;
  const isAdmin = user.role === 'admin';

  let statusLabel: string;
  let trialDaysLeft: number | null = null;

  if (isAdmin) {
    statusLabel = t('subscription.admin');
  } else if (sub?.status === 'active') {
    statusLabel = t('subscription.pro');
  } else if (sub?.status === 'trialing') {
    statusLabel = t('subscription.trial');
    if (sub.trial_ends_at) {
      trialDaysLeft = Math.max(0, Math.ceil((new Date(sub.trial_ends_at).getTime() - Date.now()) / 86_400_000));
    }
  } else {
    statusLabel = t('subscription.ended');
  }

  const canUpgrade = !isAdmin && sub?.status !== 'active';

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-5 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-1 flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-cyan-300" />
            <h3 className="text-lg font-semibold text-white">{t('subscription.title')}</h3>
          </div>
          <p className="flex items-center gap-2 text-sm text-gray-200">
            <span className="font-medium">{statusLabel}</span>
            {trialDaysLeft !== null && (
              <span className="inline-flex items-center gap-1 text-cyan-300">
                <Clock className="h-3.5 w-3.5" />
                {t('subscription.daysLeft', { days: trialDaysLeft })}
              </span>
            )}
          </p>
          <p className="mt-1 text-xs text-gray-500">{t('subscription.proBenefit')}</p>
        </div>
        {canUpgrade && (
          <button
            type="button"
            disabled
            title={t('subscription.soon')}
            className="cursor-not-allowed rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 px-5 py-2.5 font-semibold text-white opacity-60"
          >
            {t('subscription.upgrade')} · {t('subscription.soon')}
          </button>
        )}
      </div>
    </div>
  );
}
