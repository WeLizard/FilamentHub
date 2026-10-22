import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Copy, KeyRound, Loader2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { adminCatalogCurationServiceAccountAPI } from '../../api/client';
import type { CatalogCurationServiceAccount } from '../../types/api';
import { AdminPager } from './AdminPager';
import { ModalOverlay } from '../ModalOverlay';

const PAGE_SIZE = 20;
const API_PREFIX = '/api/v1';
const PROPOSALS_PATH = '/service/catalog/curation/proposals';

/** Plain English on purpose: this text is pasted into the contributor's own tooling. */
export function buildContributorInstructions(origin: string, token: string): string {
  const base = `${origin}${API_PREFIX}${PROPOSALS_PATH}`;
  return [
    'FilamentHub catalog contributor access',
    '',
    `Base URL: ${origin}${API_PREFIX}`,
    `Authorization: Bearer ${token}`,
    '',
    `Create a proposal:  POST  ${base}`,
    `List your proposals: GET   ${base}`,
    `Read one:           GET   ${base}/{id}`,
    `Edit a draft:       PATCH ${base}/{id}  (send the current "revision" in the JSON body)`,
    '',
    'The key only creates and edits this contributor\'s own drafts. An administrator reviews and applies them.',
  ].join('\n');
}

interface CatalogServiceAccountsProps {
  onClose: () => void;
}

export function CatalogServiceAccounts({ onClose }: CatalogServiceAccountsProps) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(0);
  const [name, setName] = useState('');
  const [issuedToken, setIssuedToken] = useState<string | null>(null);
  const [confirmRevokeId, setConfirmRevokeId] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const accounts = useQuery({
    queryKey: ['catalog-curation-service-accounts', page],
    queryFn: () => adminCatalogCurationServiceAccountAPI.list(page * PAGE_SIZE, PAGE_SIZE),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['catalog-curation-service-accounts'] });
  const create = useMutation({
    mutationFn: () => adminCatalogCurationServiceAccountAPI.create(name.trim()),
    onSuccess: ({ token }) => {
      setIssuedToken(token);
      setCopied(false);
      setName('');
      void refresh();
    },
  });
  const revoke = useMutation({
    mutationFn: (id: number) => adminCatalogCurationServiceAccountAPI.revoke(id),
    onSuccess: () => {
      setConfirmRevokeId(null);
      void refresh();
    },
  });

  const active = (account: CatalogCurationServiceAccount) =>
    !account.revoked_at && new Date(account.expires_at).getTime() > Date.now();
  const date = (value: string) => new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium' }).format(new Date(value));
  const instructions = issuedToken ? buildContributorInstructions(window.location.origin, issuedToken) : '';
  const totalPages = Math.ceil((accounts.data?.total ?? 0) / PAGE_SIZE);

  return (
    <ModalOverlay onClose={onClose} closeOnOverlayClick={!issuedToken} closeOnEscape={!issuedToken}
      contentClassName="flex min-h-full items-start justify-center px-4 pb-4 pt-20 sm:pt-24">
      <section role="dialog" aria-modal="true" aria-label={t('adminCatalogImport.serviceAccounts.title')}
        className="w-full max-w-xl rounded-2xl border border-white/20 bg-gray-900 p-5 shadow-2xl sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <KeyRound className="mt-0.5 h-5 w-5 shrink-0 text-indigo-300" />
            <div>
              <h3 className="text-base font-semibold text-white">{t('adminCatalogImport.serviceAccounts.title')}</h3>
              <p className="mt-1 text-sm leading-5 text-gray-400">{t('adminCatalogImport.serviceAccounts.description')}</p>
            </div>
          </div>
          {!issuedToken && <button type="button" onClick={onClose} aria-label={t('adminCatalogImport.curation.close')}
            className="rounded-lg p-1.5 text-gray-400 transition hover:bg-white/10 hover:text-white">
            <X className="h-4 w-4" />
          </button>}
        </div>

        {issuedToken ? <div className="mt-5 space-y-3">
          <p className="text-sm font-semibold text-amber-100">{t('adminCatalogImport.serviceAccounts.tokenOnce')}</p>
          <label className="block text-xs text-gray-400">{t('adminCatalogImport.serviceAccounts.token')}
            <textarea readOnly value={issuedToken} rows={2} aria-label={t('adminCatalogImport.serviceAccounts.token')}
              onFocus={(event) => event.currentTarget.select()}
              className="mt-1 block w-full resize-none break-all rounded-lg border border-amber-300/25 bg-slate-950 p-2 font-mono text-sm text-white" />
          </label>
          <div>
            <p className="text-xs text-gray-400">{t('adminCatalogImport.serviceAccounts.connect')}</p>
            <pre aria-label={t('adminCatalogImport.serviceAccounts.connect')}
              className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap break-all rounded-lg border border-white/10 bg-slate-950 p-3 text-xs leading-5 text-gray-200">{instructions}</pre>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <button type="button" onClick={async () => {
              try { await navigator.clipboard.writeText(instructions); setCopied(true); }
              catch { setCopied(false); }
            }} className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-400/40 px-3 py-2 text-sm font-semibold text-indigo-200 transition hover:bg-indigo-500/10">
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              {t(copied ? 'adminCatalogImport.serviceAccounts.copied' : 'adminCatalogImport.serviceAccounts.copyForExecutor')}
            </button>
            <button type="button" onClick={onClose}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-400">
              {t('adminCatalogImport.serviceAccounts.done')}
            </button>
          </div>
        </div> : <form className="mt-5 flex flex-wrap items-end gap-2"
          onSubmit={(event) => { event.preventDefault(); if (name.trim() && !create.isPending) create.mutate(); }}>
          <label className="min-w-0 flex-1 basis-56 text-sm text-gray-300">
            {t('adminCatalogImport.serviceAccounts.name')}
            <input value={name} maxLength={100} onChange={(event) => setName(event.target.value)}
              placeholder={t('adminCatalogImport.serviceAccounts.namePlaceholder')}
              className="mt-1 block w-full rounded-lg border border-white/15 bg-slate-950/70 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:border-indigo-400 focus:outline-none" />
          </label>
          <button type="submit" disabled={!name.trim() || create.isPending}
            className="inline-flex h-[38px] items-center rounded-lg bg-indigo-500 px-4 text-sm font-semibold text-white disabled:opacity-40">
            {create.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : t('adminCatalogImport.serviceAccounts.create')}
          </button>
        </form>}
        {create.isError && <p role="alert" className="mt-2 text-sm text-red-300">{t('adminCatalogImport.serviceAccounts.createError')}</p>}

        {(accounts.isLoading || accounts.isError || (accounts.data?.items.length ?? 0) > 0) && <div className="mt-5 space-y-1.5 border-t border-white/10 pt-4">
          {accounts.isLoading && <Loader2 className="h-4 w-4 animate-spin text-gray-400" />}
          {accounts.isError && <button type="button" onClick={() => void accounts.refetch()} className="text-sm text-red-300">
            {t('adminCatalogImport.serviceAccounts.listError')}
          </button>}
          {accounts.data?.items.map((account) => <div key={account.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white/[0.04] px-3 py-2 text-sm">
            <div className="min-w-0 truncate">
              <span className="font-medium text-white">{account.name}</span>
              <span className="ml-2 text-xs text-gray-400">#{account.id} · {t('adminCatalogImport.serviceAccounts.expires', { date: date(account.expires_at) })}</span>
            </div>
            {active(account) ? confirmRevokeId === account.id ? <span className="flex items-center gap-2">
              <span className="text-xs text-amber-200">{t('adminCatalogImport.serviceAccounts.confirmRevoke')}</span>
              <button type="button" disabled={revoke.isPending} onClick={() => revoke.mutate(account.id)} className="text-xs font-semibold text-red-300 disabled:opacity-40">{t('adminCatalogImport.serviceAccounts.revoke')}</button>
              <button type="button" onClick={() => setConfirmRevokeId(null)} className="text-xs text-gray-300">{t('adminCatalogImport.serviceAccounts.cancel')}</button>
            </span> : <button type="button" onClick={() => setConfirmRevokeId(account.id)} className="text-xs text-red-300 hover:text-red-200">{t('adminCatalogImport.serviceAccounts.revoke')}</button>
              : <span className="text-xs text-gray-500">{t(account.revoked_at ? 'adminCatalogImport.serviceAccounts.revoked' : 'adminCatalogImport.serviceAccounts.expired')}</span>}
          </div>)}
          {revoke.isError && <p role="alert" className="text-sm text-red-300">{t('adminCatalogImport.serviceAccounts.revokeError')}</p>}
          <div className="pt-1">
            <AdminPager page={page + 1} totalPages={totalPages} onPageChange={(value) => setPage(value - 1)}
              label={t('adminCatalogImport.serviceAccounts.title')}
              previousLabel={t('adminCatalogImport.curation.previous')} nextLabel={t('adminCatalogImport.curation.next')} />
          </div>
        </div>}
      </section>
    </ModalOverlay>
  );
}
