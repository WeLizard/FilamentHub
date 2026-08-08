/** Кто ведёт бренд в своей стране — и как позвать нового. */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Globe2, Link2, MailPlus, Trash2 } from 'lucide-react';

import { brandRepresentativesAPI } from '../api/client';
import { COUNTRY_CODES, countryName } from '../utils/countries';
import { translateApiError } from '../utils/translateApiError';
import { ConfirmDeleteModal } from './ConfirmDeleteModal';
import { toast } from './Toast';
import type { AxiosError } from 'axios';

interface BrandRepresentativesPanelProps {
  brandId: number;
}

function apiErrorDetail(error: unknown): unknown {
  return (error as AxiosError<{ detail?: unknown }>).response?.data?.detail;
}

export function BrandRepresentativesPanel({ brandId }: BrandRepresentativesPanelProps) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [country, setCountry] = useState('');
  const [organizationName, setOrganizationName] = useState('');
  const [pendingRevoke, setPendingRevoke] = useState<{ id: number; label: string } | null>(null);

  const query = useQuery({
    queryKey: ['brand-representatives', brandId],
    queryFn: () => brandRepresentativesAPI.list(brandId),
    retry: false,
  });

  const inviteMutation = useMutation({
    mutationFn: (sendEmail: boolean) => brandRepresentativesAPI.invite(brandId, {
      email,
      country,
      organization_name: organizationName,
      send_email: sendEmail,
    }),
    onSuccess: async (invite, sendEmail) => {
      if (!sendEmail) {
        await navigator.clipboard.writeText(invite.invite_url);
      }
      setEmail('');
      setOrganizationName('');
      await queryClient.invalidateQueries({ queryKey: ['brand-representatives', brandId] });
      toast.success(t(sendEmail ? 'brandReps.invited' : 'brandReps.linkCopied'));
    },
    onError: (error) => toast.error(
      translateApiError(t, apiErrorDetail(error), t('brandReps.actionError')),
    ),
  });

  const revokeMutation = useMutation({
    mutationFn: (grantId: number) => brandRepresentativesAPI.revoke(brandId, grantId),
    onSuccess: async () => {
      setPendingRevoke(null);
      await queryClient.invalidateQueries({ queryKey: ['brand-representatives', brandId] });
      toast.success(t('brandReps.revoked'));
    },
    onError: (error) => toast.error(
      translateApiError(t, apiErrorDetail(error), t('brandReps.actionError')),
    ),
  });

  // Отказ означает, что приглашать представителей этот человек не вправе.
  if (query.isError || query.isLoading) {
    return null;
  }

  const representatives = query.data ?? [];
  const canSubmit = Boolean(email.trim() && country && organizationName.trim());

  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
      <div className="mb-1 flex items-center gap-2">
        <Globe2 className="h-5 w-5 text-emerald-300" />
        <h4 className="font-semibold text-white">{t('brandReps.title')}</h4>
      </div>
      <p className="mb-4 text-xs leading-5 text-gray-400">{t('brandReps.explained')}</p>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_170px_minmax(0,1fr)_auto]">
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder={t('brandReps.emailPlaceholder')}
          className="min-w-0 rounded-xl border border-white/15 bg-slate-950/45 px-4 py-3 text-white outline-none transition placeholder:text-gray-500 focus:border-emerald-300/60"
        />
        <select
          value={country}
          onChange={(event) => setCountry(event.target.value)}
          className="rounded-xl border border-white/15 bg-slate-950 px-3 py-3 text-white outline-none focus:border-emerald-300/60"
        >
          <option value="">{t('brandReps.countryPlaceholder')}</option>
          {COUNTRY_CODES.map((code) => (
            <option key={code} value={code}>
              {countryName(code, i18n.language)}
            </option>
          ))}
        </select>
        <input
          type="text"
          value={organizationName}
          onChange={(event) => setOrganizationName(event.target.value)}
          placeholder={t('brandReps.companyPlaceholder')}
          maxLength={200}
          className="min-w-0 rounded-xl border border-white/15 bg-slate-950/45 px-4 py-3 text-white outline-none transition placeholder:text-gray-500 focus:border-emerald-300/60"
        />
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => inviteMutation.mutate(true)}
            disabled={!canSubmit || inviteMutation.isPending}
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-3 font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-40"
          >
            <MailPlus className="h-4 w-4" /> {t('brandReps.invite')}
          </button>
          <button
            type="button"
            onClick={() => inviteMutation.mutate(false)}
            disabled={!canSubmit || inviteMutation.isPending}
            title={t('brandReps.copyLink')}
            className="rounded-xl border border-white/15 bg-white/5 px-3 text-gray-200 transition hover:bg-white/10 disabled:opacity-40"
          >
            <Link2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="mt-5 divide-y divide-white/10">
        {representatives.length === 0 && (
          <p className="py-3 text-sm text-gray-400">{t('brandReps.empty')}</p>
        )}
        {representatives.map((item) => (
          <div key={item.grant_id} className="flex flex-wrap items-center gap-3 py-3">
            <span className="text-sm font-medium text-white">
              {item.country ? countryName(item.country, i18n.language) : t('brandReps.everywhere')}
            </span>
            <span className="text-sm text-gray-400">{item.organization_name}</span>
            {item.country && (
              <button
                type="button"
                onClick={() => setPendingRevoke({
                  id: item.grant_id,
                  label: `${countryName(item.country!, i18n.language)} · ${item.organization_name}`,
                })}
                className="ml-auto inline-flex items-center gap-1.5 text-xs text-gray-400 transition hover:text-red-300"
              >
                <Trash2 className="h-3.5 w-3.5" /> {t('brandReps.revoke')}
              </button>
            )}
          </div>
        ))}
      </div>

      {pendingRevoke && (
        <ConfirmDeleteModal
          isOpen
          onClose={() => setPendingRevoke(null)}
          onConfirm={() => revokeMutation.mutate(pendingRevoke.id)}
          title={t('brandReps.revokeTitle')}
          message={t('brandReps.revokeMessage', { target: pendingRevoke.label })}
          confirmText={t('brandReps.revoke')}
          isLoading={revokeMutation.isPending}
        />
      )}
    </section>
  );
}
