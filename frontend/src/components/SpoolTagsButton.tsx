import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Nfc, PenLine, Radio, Trash2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  spoolQrAPI,
  spoolTagsAPI,
  type SpoolTagCreatePayload,
  type SpoolTagTechnology,
  type UserSpool,
} from '../api/client';
import { edgeTagStationErrorText, useEdgeTagStation } from '../hooks/useEdgeTagStation';
import {
  EdgeTagStationError,
  isWritableTag,
  spoolTagUris,
  writeSpoolUri,
  type EdgeTagRead,
  type EdgeTagStation,
} from '../utils/edgeTagStation';
import { translateApiError } from '../utils/translateApiError';
import { ConfirmModal } from './ConfirmModal';
import { ModalOverlay } from './ModalOverlay';
import { toast } from './Toast';

type ApiFailure = { response?: { data?: { detail?: unknown } } };

/** The kit guide's section on writing and using spool tags. */
const EDGE_TAGS_GUIDE = '/download/edge#edge-kit-tags';

// Every action in the dialog reports, also when it repeats: one channel for all.
const TOAST_KEY = 'spool-tags';

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
    toast.error(translateApiError(t, detail, t('spoolTags.error')), undefined, TOAST_KEY);
  };

  const link = useMutation({
    mutationFn: (payload: SpoolTagCreatePayload) => spoolTagsAPI.link(spool.id, payload),
    onSuccess: async () => {
      setUid('');
      setFormat('');
      await queryClient.invalidateQueries({ queryKey });
      toast.success(t('spoolTags.linked'), undefined, TOAST_KEY);
    },
    onError: showError,
  });

  const unlink = useMutation({
    mutationFn: (tagUid: string) => spoolTagsAPI.unlink(spool.id, tagUid),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey });
      toast.success(t('spoolTags.unlinked'), undefined, TOAST_KEY);
    },
    onError: showError,
  });

  const pending = link.isPending || unlink.isPending;
  const name = spool.filament?.name ?? t('profilePage.spoolNoFilament');

  const edge = useEdgeTagStation();
  const [overwrite, setOverwrite] = useState<{ tag: EdgeTagRead; uris: string[] } | null>(null);
  const stationBusy = pending || edge.status === 'connecting' || edge.status === 'working';

  const close = () => {
    setOpen(false);
    setOverwrite(null);
    void edge.disconnect();
  };

  const showStationError = (error: unknown) => {
    const text = edgeTagStationErrorText(t, error);
    if (text) toast.error(text, undefined, TOAST_KEY);
    else showError(error);
  };

  // A tag that already belongs to another spool is never taken over silently.
  const tagOwner = async (uid: string): Promise<'this' | 'free'> => {
    const resolved = await spoolTagsAPI.resolve(uid);
    if (resolved.status === 'matched' && resolved.spool_id !== spool.id) {
      throw new EdgeTagStationError('linked_elsewhere');
    }
    return resolved.status === 'matched' ? 'this' : 'free';
  };

  const linkStationTag = async (tag: EdgeTagRead) => {
    // Every tag the kit reads is high-frequency: NTAG/ISO14443A or ISO15693.
    await spoolTagsAPI.link(spool.id, { uid: tag.uid, technology: 'nfc', format: tag.type });
    await queryClient.invalidateQueries({ queryKey });
  };

  const readAndLink = () => {
    edge.run(async (station) => {
      const tag = await station.read();
      if (await tagOwner(tag.uid) === 'this') {
        toast.info(t('edgeTags.alreadyLinked'), undefined, TOAST_KEY);
        return;
      }
      await linkStationTag(tag);
      toast.success(t('spoolTags.linked'), undefined, TOAST_KEY);
    }).catch(showStationError);
  };

  const finishWrite = async (station: EdgeTagStation, tag: EdgeTagRead, uris: string[]) => {
    const owner = await tagOwner(tag.uid);
    if (!tag.uri || !uris.includes(tag.uri)) await writeSpoolUri(station, tag, uris);
    if (owner === 'free') await linkStationTag(tag);
    toast.success(t('edgeTags.written'), undefined, TOAST_KEY);
  };

  const writeToTag = () => {
    edge.run(async (station) => {
      const tag = await station.read();
      if (!isWritableTag(tag)) throw new EdgeTagStationError('not_writable');
      await tagOwner(tag.uid);
      const identity = await spoolQrAPI.issue(spool.id);
      const uris = spoolTagUris(identity.target_url, identity.short_code, window.location.origin);
      if (tag.uri && !uris.includes(tag.uri)) {
        setOverwrite({ tag, uris });
        return;
      }
      await finishWrite(station, tag, uris);
    }).catch(showStationError);
  };

  const confirmOverwrite = () => {
    const confirmed = overwrite;
    setOverwrite(null);
    if (!confirmed) return;
    // The kit writes only to the UID read before, so a swapped tag is refused.
    edge.run((station) => finishWrite(station, confirmed.tag, confirmed.uris)).catch(showStationError);
  };

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
        <ModalOverlay onClose={close}>
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
                onClick={close}
                title={t('common.close')}
                className="rounded p-1 text-gray-400 transition hover:bg-white/10 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {edge.supported && (
              <div className="mt-4 rounded-xl border border-cyan-400/20 bg-cyan-400/5 p-3">
                <div className="flex items-start gap-2">
                  <Nfc className="mt-0.5 h-4 w-4 shrink-0 text-cyan-300" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-white">{t('edgeTags.title')}</p>
                    <p className="mt-0.5 text-[11px] text-gray-400">
                      {t(edge.status === 'connecting'
                        ? 'edgeTags.connecting'
                        : edge.status === 'idle' ? 'edgeTags.hint' : 'edgeTags.connected')}
                    </p>
                    <a
                      href={EDGE_TAGS_GUIDE}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1 inline-block text-[11px] text-cyan-300 underline hover:text-cyan-200"
                    >
                      {t('edgeTags.guideLink')}
                    </a>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={readAndLink}
                    disabled={stationBusy}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/30 bg-cyan-400/10 px-3 py-1.5 text-xs font-medium text-cyan-100 transition hover:bg-cyan-400/20 disabled:opacity-50"
                  >
                    {edge.status === 'connecting' || edge.status === 'working'
                      ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      : <Nfc className="h-3.5 w-3.5" />}
                    {t('edgeTags.readAndLink')}
                  </button>
                  <button
                    type="button"
                    onClick={writeToTag}
                    disabled={stationBusy}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/30 bg-cyan-400/10 px-3 py-1.5 text-xs font-medium text-cyan-100 transition hover:bg-cyan-400/20 disabled:opacity-50"
                  >
                    <PenLine className="h-3.5 w-3.5" />
                    {t('edgeTags.write')}
                  </button>
                  {edge.status === 'ready' && (
                    <button
                      type="button"
                      onClick={() => void edge.disconnect()}
                      className="px-1 text-xs text-gray-400 transition hover:text-white"
                    >
                      {t('edgeTags.disconnect')}
                    </button>
                  )}
                </div>
              </div>
            )}

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
      <ConfirmModal
        isOpen={overwrite !== null}
        onClose={() => setOverwrite(null)}
        onConfirm={confirmOverwrite}
        title={t('edgeTags.overwriteTitle')}
        message={t('edgeTags.overwriteMessage', { uri: overwrite?.tag.uri ?? '' })}
        confirmText={t('edgeTags.overwriteConfirm')}
        variant="warning"
      />
    </>
  );
}
