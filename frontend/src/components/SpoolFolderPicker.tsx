import { useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { Folder, FolderPlus, Loader2, X } from 'lucide-react';

import { spoolsAPI, type SpoolCollection, type UserSpool } from '../api/client';
import { ModalOverlay } from './ModalOverlay';
import { showSpoolFolderError } from './SpoolFolderBar';
import { spoolQueryKeys } from '../utils/spoolQueries';

interface SpoolFolderPickerProps {
  spool: UserSpool;
  collections: SpoolCollection[];
  userId: number | null | undefined;
  onClose: () => void;
}

export function SpoolFolderPicker({ spool, collections, userId, onClose }: SpoolFolderPickerProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [memberIds, setMemberIds] = useState<Set<number>>(() => new Set(spool.collection_ids ?? []));
  const [pendingIds, setPendingIds] = useState<Set<number>>(() => new Set());
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);
  const changed = useRef(false);

  const displayName = spool.filament?.name || spool.extra?.display_name || t('profilePage.spoolNoFilament');

  const setMember = (id: number, member: boolean) => {
    setMemberIds((prev) => {
      const next = new Set(prev);
      if (member) next.add(id);
      else next.delete(id);
      return next;
    });
  };
  const setPending = (id: number, pending: boolean) => {
    setPendingIds((prev) => {
      const next = new Set(prev);
      if (pending) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const toggle = async (folderId: number) => {
    if (pendingIds.has(folderId)) return;
    const add = !memberIds.has(folderId);
    setMember(folderId, add);
    setPending(folderId, true);
    try {
      await spoolsAPI.updateCollectionMembers(folderId, add ? { add: [spool.id] } : { remove: [spool.id] });
      changed.current = true;
      void queryClient.invalidateQueries({ queryKey: spoolQueryKeys.collections(userId) });
    } catch (error) {
      setMember(folderId, !add);
      showSpoolFolderError(t, error);
    } finally {
      setPending(folderId, false);
    }
  };

  const create = async (event: FormEvent) => {
    event.preventDefault();
    const name = newName.trim();
    if (!name || creating) return;
    setCreating(true);
    try {
      const folder = await spoolsAPI.createCollection(name);
      changed.current = true;
      await spoolsAPI.updateCollectionMembers(folder.id, { add: [spool.id] });
      setMember(folder.id, true);
      setNewName('');
      await queryClient.invalidateQueries({ queryKey: spoolQueryKeys.collections(userId) });
    } catch (error) {
      showSpoolFolderError(t, error);
    } finally {
      setCreating(false);
    }
  };

  const close = () => {
    if (changed.current) void queryClient.invalidateQueries({ queryKey: spoolQueryKeys.root });
    onClose();
  };

  return (
    <ModalOverlay onClose={close}>
      <div
        role="dialog"
        aria-label={t('profilePage.spoolShelf.pickerTitle')}
        className="glass-panel w-full max-w-sm rounded-2xl border border-white/20 p-4 shadow-xl"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="flex items-center gap-2 text-base font-semibold text-white">
              <Folder className="h-4 w-4 text-purple-300" aria-hidden />
              {t('profilePage.spoolShelf.pickerTitle')}
            </h3>
            <p className="mt-0.5 truncate text-xs text-gray-400">{displayName}</p>
          </div>
          <button
            type="button"
            onClick={close}
            title={t('common.close')}
            aria-label={t('common.close')}
            className="rounded-lg p-1 text-gray-400 transition hover:bg-white/10 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {collections.length === 0 ? (
          <p className="rounded-xl border border-white/10 bg-white/5 px-3 py-3 text-xs text-gray-400">
            {t('profilePage.spoolShelf.pickerEmpty')}
          </p>
        ) : (
          <ul className="max-h-[50vh] space-y-1 overflow-y-auto pr-1">
            {collections.map((folder) => {
              const checked = memberIds.has(folder.id);
              const pending = pendingIds.has(folder.id);
              return (
                <li key={folder.id}>
                  <label
                    className={`flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                      checked ? 'bg-purple-500/15 text-white' : 'text-gray-300 hover:bg-white/5'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={pending}
                      onChange={() => void toggle(folder.id)}
                      className="h-4 w-4 flex-shrink-0 accent-purple-500"
                    />
                    <span className="min-w-0 flex-1 truncate">{folder.name}</span>
                    {pending && <Loader2 className="h-3.5 w-3.5 flex-shrink-0 animate-spin text-gray-400" />}
                  </label>
                </li>
              );
            })}
          </ul>
        )}

        <form onSubmit={create} className="mt-3 flex items-center gap-2 border-t border-white/10 pt-3">
          <input
            value={newName}
            maxLength={100}
            onChange={(event) => setNewName(event.target.value)}
            placeholder={t('profilePage.spoolShelf.newFolder')}
            aria-label={t('profilePage.spoolShelf.newFolder')}
            disabled={creating}
            className="min-w-0 flex-1 rounded-lg border border-white/20 bg-white/5 px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={creating || !newName.trim()}
            className="inline-flex flex-shrink-0 items-center gap-1.5 rounded-lg border border-white/20 bg-white/5 px-3 py-1.5 text-sm text-gray-200 transition hover:bg-white/10 disabled:opacity-50"
          >
            {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <FolderPlus className="h-4 w-4" />}
            {t('profilePage.spoolShelf.create')}
          </button>
        </form>
      </div>
    </ModalOverlay>
  );
}

interface SpoolFolderChipsProps {
  folders: SpoolCollection[];
  onClick?: () => void;
  max?: number;
  className?: string;
}

export function SpoolFolderChips({ folders, onClick, max, className = '' }: SpoolFolderChipsProps) {
  const { t } = useTranslation();
  if (folders.length === 0) return null;
  const visible = max ? folders.slice(0, max) : folders;
  const hidden = folders.length - visible.length;
  const chip = 'inline-flex max-w-[10rem] items-center gap-1 rounded-md border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] text-gray-300';
  return (
    <div className={`flex min-w-0 flex-wrap items-center gap-1 ${className}`}>
      {visible.map((folder) => (
        <button
          key={folder.id}
          type="button"
          onClick={onClick}
          disabled={!onClick}
          title={t('profilePage.spoolShelf.putInFolder')}
          className={`${chip} transition hover:bg-white/10 disabled:cursor-default disabled:hover:bg-white/5`}
        >
          <Folder className="h-2.5 w-2.5 flex-shrink-0 text-purple-300" aria-hidden />
          <span className="truncate">{folder.name}</span>
        </button>
      ))}
      {hidden > 0 && <span className={chip}>+{hidden}</span>}
    </div>
  );
}
