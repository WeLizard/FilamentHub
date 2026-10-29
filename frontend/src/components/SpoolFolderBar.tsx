import { useState, type FormEvent, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { Check, Folder, Loader2, Pencil, Plus, Trash2, X } from 'lucide-react';

import { spoolsAPI, type SpoolCollection, type SpoolFeedParams } from '../api/client';
import { ConfirmDeleteModal } from './ConfirmDeleteModal';
import { toast } from './Toast';
import { translateApiError } from '../utils/translateApiError';
import { spoolQueryKeys } from '../utils/spoolQueries';
import { readUiPreference, uiScopeForUser, writeUiPreference } from '../utils/uiPreferences';

export type SpoolFolderFilter = 'all' | 'none' | number;

const FOLDER_NAME_MAX = 100;

export function showSpoolFolderError(t: ReturnType<typeof useTranslation>['t'], error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  toast.error(translateApiError(t, detail), undefined, 'spool-folders');
}

export function spoolFolderParams(filter: SpoolFolderFilter): Pick<SpoolFeedParams, 'collection_id' | 'no_collection'> {
  if (filter === 'none') return { no_collection: true };
  if (typeof filter === 'number') return { collection_id: filter };
  return {};
}

/**
 * Remembers the selected folder per user. A folder that no longer exists
 * falls back to "all" once the folder list is known.
 */
export function useSpoolFolderFilter(
  preferenceKey: string,
  userId: number | null | undefined,
  collections: SpoolCollection[] | undefined,
): [SpoolFolderFilter, (filter: SpoolFolderFilter) => void] {
  const scope = uiScopeForUser(userId);
  const [stored, setStored] = useState<{ scope: string; value: string | null }>(() => ({
    scope,
    value: readUiPreference(scope, preferenceKey),
  }));
  const raw = stored.scope === scope ? stored.value : readUiPreference(scope, preferenceKey);

  let filter: SpoolFolderFilter = 'all';
  if (raw === 'none') {
    filter = 'none';
  } else if (raw && /^\d+$/.test(raw)) {
    const id = Number(raw);
    if (!collections || collections.some((item) => item.id === id)) filter = id;
  }

  const setFilter = (next: SpoolFolderFilter) => {
    const value = String(next);
    writeUiPreference(scope, preferenceKey, value);
    setStored({ scope, value });
  };

  return [filter, setFilter];
}

interface FolderNameInputProps {
  initialValue?: string;
  busy: boolean;
  placeholder: string;
  onSubmit: (name: string) => void;
  onCancel: () => void;
}

function FolderNameInput({ initialValue = '', busy, placeholder, onSubmit, onCancel }: FolderNameInputProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState(initialValue);

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const name = value.trim();
    if (!name || busy) return;
    onSubmit(name);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      onCancel();
    }
  };

  return (
    <form onSubmit={submit} className="inline-flex items-center gap-1 rounded-lg border border-purple-400/60 bg-black/20 py-0.5 pl-2 pr-0.5">
      <input
        autoFocus
        value={value}
        maxLength={FOLDER_NAME_MAX}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        aria-label={placeholder}
        disabled={busy}
        className="w-36 bg-transparent text-sm text-white placeholder-gray-500 focus:outline-none sm:w-44"
      />
      <button
        type="submit"
        disabled={busy || !value.trim()}
        title={t('common.save')}
        aria-label={t('common.save')}
        className="rounded-md p-1 text-purple-200 transition hover:bg-white/10 disabled:opacity-40"
      >
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
      </button>
      <button
        type="button"
        onClick={onCancel}
        disabled={busy}
        title={t('common.cancel')}
        aria-label={t('common.cancel')}
        className="rounded-md p-1 text-gray-400 transition hover:bg-white/10 hover:text-white"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </form>
  );
}

interface SpoolFolderBarProps {
  collections: SpoolCollection[];
  selected: SpoolFolderFilter;
  onSelect: (filter: SpoolFolderFilter) => void;
}

const chipClass = (active: boolean) => [
  'inline-flex max-w-full items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition-colors',
  active
    ? 'border-purple-400/70 bg-purple-500/20 text-white'
    : 'border-white/10 bg-white/5 text-gray-300 hover:bg-white/10',
].join(' ');

export function SpoolFolderBar({ collections, selected, onSelect }: SpoolFolderBarProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<'idle' | 'create' | 'rename'>('idle');
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState<SpoolCollection | null>(null);

  const selectedFolder = typeof selected === 'number'
    ? collections.find((item) => item.id === selected) ?? null
    : null;

  const refresh = () => queryClient.invalidateQueries({ queryKey: spoolQueryKeys.root });

  const create = async (name: string) => {
    setBusy(true);
    try {
      await spoolsAPI.createCollection(name);
      setMode('idle');
      await refresh();
    } catch (error) {
      showSpoolFolderError(t, error);
    } finally {
      setBusy(false);
    }
  };

  const rename = async (name: string) => {
    if (!selectedFolder) return;
    if (name === selectedFolder.name) {
      setMode('idle');
      return;
    }
    setBusy(true);
    try {
      await spoolsAPI.renameCollection(selectedFolder.id, name);
      setMode('idle');
      await refresh();
    } catch (error) {
      showSpoolFolderError(t, error);
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    setBusy(true);
    try {
      await spoolsAPI.deleteCollection(deleting.id);
      if (selected === deleting.id) onSelect('all');
      setDeleting(null);
      await refresh();
    } catch (error) {
      showSpoolFolderError(t, error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={t('profilePage.spoolShelf.folders')}>
      <Folder className="mr-0.5 h-4 w-4 flex-shrink-0 text-gray-500" aria-hidden />
      <button type="button" onClick={() => onSelect('all')} aria-pressed={selected === 'all'} className={chipClass(selected === 'all')}>
        {t('profilePage.spoolShelf.allSpools')}
      </button>
      <button type="button" onClick={() => onSelect('none')} aria-pressed={selected === 'none'} className={chipClass(selected === 'none')}>
        {t('profilePage.spoolShelf.noFolder')}
      </button>

      {collections.map((folder) => {
        const active = selected === folder.id;
        if (active && mode === 'rename') {
          return (
            <FolderNameInput
              key={folder.id}
              initialValue={folder.name}
              busy={busy}
              placeholder={t('profilePage.spoolShelf.folderNamePlaceholder')}
              onSubmit={(name) => void rename(name)}
              onCancel={() => setMode('idle')}
            />
          );
        }
        return (
          <div
            key={folder.id}
            className={`inline-flex max-w-full items-center rounded-lg ${active ? 'bg-purple-500/20 ring-1 ring-purple-400/70' : ''}`}
          >
            <button
              type="button"
              onClick={() => onSelect(folder.id)}
              aria-pressed={active}
              className={active
                ? 'inline-flex min-w-0 items-center gap-1.5 px-2.5 py-1 text-xs text-white'
                : chipClass(false)}
            >
              <span className="truncate">{folder.name}</span>
              <span className="rounded-full bg-black/25 px-1.5 text-[10px] text-gray-300">{folder.spool_count}</span>
            </button>
            {active && (
              <>
                <button
                  type="button"
                  onClick={() => setMode('rename')}
                  title={t('profilePage.spoolShelf.renameFolder')}
                  aria-label={t('profilePage.spoolShelf.renameFolder')}
                  className="rounded-md p-1 text-gray-300 transition hover:bg-white/10 hover:text-white"
                >
                  <Pencil className="h-3 w-3" />
                </button>
                <button
                  type="button"
                  onClick={() => setDeleting(folder)}
                  title={t('profilePage.spoolShelf.deleteFolder')}
                  aria-label={t('profilePage.spoolShelf.deleteFolder')}
                  className="mr-0.5 rounded-md p-1 text-red-300 transition hover:bg-red-500/20"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </>
            )}
          </div>
        );
      })}

      {mode === 'create' ? (
        <FolderNameInput
          busy={busy}
          placeholder={t('profilePage.spoolShelf.folderNamePlaceholder')}
          onSubmit={(name) => void create(name)}
          onCancel={() => setMode('idle')}
        />
      ) : (
        <button
          type="button"
          onClick={() => setMode('create')}
          title={t('profilePage.spoolShelf.newFolder')}
          aria-label={t('profilePage.spoolShelf.newFolder')}
          className="inline-flex items-center gap-1 rounded-lg border border-dashed border-white/20 px-2 py-1 text-xs text-gray-400 transition hover:border-white/40 hover:text-white"
        >
          <Plus className="h-3.5 w-3.5" />
          {collections.length === 0 && <span>{t('profilePage.spoolShelf.newFolder')}</span>}
        </button>
      )}

      <ConfirmDeleteModal
        isOpen={deleting !== null}
        onClose={() => setDeleting(null)}
        onConfirm={() => void confirmDelete()}
        isLoading={busy}
        title={t('profilePage.spoolShelf.deleteFolder')}
        message={t('profilePage.spoolShelf.deleteFolderMessage', { name: deleting?.name ?? '' })}
      />
    </div>
  );
}
