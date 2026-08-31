import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Radio, Trash2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  spoolTagsAPI,
  type SpoolTagCreatePayload,
  type SpoolTagTechnology,
  type UserSpool,
} from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { ModalOverlay } from './ModalOverlay';
import { toast } from './Toast';

type ApiFailure = { response?: { data?: { detail?: unknown } } };

export function SpoolTagsButton({
  spool,
  compact = false,
  busy = false,
}: {
  spool: Pick<UserSpool, 'id' | 'filament'>;
  compact?: boolean;
  busy?: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [uid, setUid] = useState('');
  const [technology, setTechnology] = useState<SpoolTagTechnology>('unknown');
  const [format, setFormat] = useState('');

  const queryKey = ['spool-tags', spool.id] as const;
  const { data: tags = [], isLoading } = useQuery({
    queryKey,
    queryFn: () => spoolTagsAPI.list(spool.id),
    enabled: open,
  });

  const showError = (error: unknown) => {
    const detail = (error as ApiFailure)?.response?.data?.detail;
    toast.error(translateApiError(t, detail, t('spoolTags.error')));
  };

  const link = useMutation({
    mutationFn: (payload: SpoolTagCreatePayload) => spoolTagsAPI.link(spool.id, payload),
    onSuccess: async () => {
      setUid('');
      setFormat('');
      await queryClient.invalidateQueries({ queryKey });
      toast.success(t('spoolTags.linked'));
    },
    onError: showError,
  });

  const unlink = useMutation({
    mutationFn: (tagUid: string) => spoolTagsAPI.unlink(spool.id, tagUid),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey });
      toast.success(t('spoolTags.unlinked'));
    },
    onError: showError,
  });

  const pending = link.isPending || unlink.isPending;
  const name = spool.filament?.name ?? t('profilePage.spoolNoFilament');

  return (
    <>
      <button
        type="button"
        disabled={busy}
        onClick={() => setOpen(true)}
        aria-label={t('spoolTags.action')}
        title={t('spoolTags.action')}
        className={
          compact
            ? 'rounded-lg p-1.5 text-gray-300 transition hover:bg-white/10 hover:text-white disabled:opacity-40'
            : 'inline-flex items-center justify-center gap-1 rounded-lg border border-violet-400/25 bg-violet-400/10 px-2 py-1 text-[11px] text-violet-100 hover:bg-violet-400/20 disabled:opacity-40'
        }
      >
        <Radio className="h-3.5 w-3.5" />
        {!compact && t('spoolTags.shortAction')}
      </button>

      {open && (
        <ModalOverlay onClose={() => setOpen(false)}>
          <div className="w-full max-w-lg rounded-2xl border border-white/20 bg-gray-900 p-5 shadow-xl">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="truncate text-base font-semibold text-white">
                  {t('spoolTags.title', { name })}
                </h3>
                <p className="mt-1 text-xs text-gray-400">{t('spoolTags.description')}</p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                title={t('common.close')}
                className="rounded p-1 text-gray-400 transition hover:bg-white/10 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form
              className="mt-4 space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                if (!uid.trim()) return;
                link.mutate({
                  uid: uid.trim(),
                  technology,
                  format: format.trim() || null,
                });
              }}
            >
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-300" htmlFor={`spool-tag-uid-${spool.id}`}>
                  {t('spoolTags.uid')}
                </label>
                <input
                  id={`spool-tag-uid-${spool.id}`}
                  value={uid}
                  onChange={(event) => setUid(event.target.value)}
                  maxLength={128}
                  autoComplete="off"
                  spellCheck={false}
                  placeholder={t('spoolTags.uidPlaceholder')}
                  className="w-full rounded-lg border border-white/20 bg-white/5 px-3 py-2 font-mono text-sm text-white outline-none focus:border-violet-400"
                />
                <p className="mt-1 text-[11px] text-gray-500">{t('spoolTags.uidHint')}</p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-300" htmlFor={`spool-tag-tech-${spool.id}`}>
                    {t('spoolTags.technology')}
                  </label>
                  <select
                    id={`spool-tag-tech-${spool.id}`}
                    value={technology}
                    onChange={(event) => setTechnology(event.target.value as SpoolTagTechnology)}
                    className="w-full rounded-lg border border-white/20 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-violet-400"
                  >
                    <option value="unknown">{t('spoolTags.technologyUnknown')}</option>
                    <option value="nfc">NFC / HF RFID</option>
                    <option value="uhf_rfid">UHF RFID</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-300" htmlFor={`spool-tag-format-${spool.id}`}>
                    {t('spoolTags.format')}
                  </label>
                  <input
                    id={`spool-tag-format-${spool.id}`}
                    value={format}
                    onChange={(event) => setFormat(event.target.value)}
                    maxLength={32}
                    placeholder={t('spoolTags.formatPlaceholder')}
                    className="w-full rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-violet-400"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={!uid.trim() || pending}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-violet-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-violet-500 disabled:opacity-50"
              >
                {link.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                {t('spoolTags.link')}
              </button>
            </form>

            <div className="mt-5 border-t border-white/10 pt-4">
              <h4 className="text-xs font-medium uppercase tracking-wide text-gray-400">
                {t('spoolTags.linkedTags')}
              </h4>
              {isLoading ? (
                <div className="flex justify-center py-5">
                  <Loader2 className="h-5 w-5 animate-spin text-violet-400" />
                </div>
              ) : tags.length === 0 ? (
                <p className="py-4 text-sm text-gray-500">{t('spoolTags.empty')}</p>
              ) : (
                <div className="mt-2 space-y-2">
                  {tags.map((tag) => (
                    <div key={tag.id} className="flex items-center gap-3 rounded-lg bg-white/5 px-3 py-2">
                      <Radio className="h-4 w-4 shrink-0 text-violet-300" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-mono text-sm text-gray-100">{tag.uid}</p>
                        <p className="text-[11px] text-gray-500">
                          {t(`spoolTags.technologyLabel.${tag.technology}`)}
                          {tag.format ? ` · ${tag.format}` : ''}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => unlink.mutate(tag.uid)}
                        disabled={pending}
                        title={t('spoolTags.unlink')}
                        className="rounded p-1.5 text-red-300 transition hover:bg-red-500/20 disabled:opacity-50"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </ModalOverlay>
      )}
    </>
  );
}
