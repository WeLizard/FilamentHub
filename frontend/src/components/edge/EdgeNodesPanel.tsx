import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Pencil, Router, Trash2, X } from 'lucide-react';
import { edgeNodesAPI, type EdgeNode } from '../../api/client';
import { ConfirmDeleteModal } from '../ConfirmDeleteModal';
import { toast } from '../Toast';
import { formatDateTime } from '../../utils/formatDate';
import { translateApiError } from '../../utils/translateApiError';

export const EDGE_NODES_QUERY_KEY = ['edge-nodes'] as const;

/** The account's own Edge nodes. Renders nothing until there is at least one. */
export function EdgeNodesPanel() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [renaming, setRenaming] = useState<{ id: number; name: string } | null>(null);
  const [removing, setRemoving] = useState<EdgeNode | null>(null);

  // Read when the profile opens; a node's state does not need watching.
  const { data: nodes = [] } = useQuery({ queryKey: EDGE_NODES_QUERY_KEY, queryFn: edgeNodesAPI.list });
  const refresh = () => queryClient.invalidateQueries({ queryKey: EDGE_NODES_QUERY_KEY });
  const onError = (error: unknown) => {
    const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
    toast.error(translateApiError(t, detail, t('common.error')));
  };

  const rename = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => edgeNodesAPI.rename(id, name),
    onSuccess: () => { setRenaming(null); void refresh(); },
    onError,
  });
  const remove = useMutation({
    mutationFn: (id: number) => edgeNodesAPI.remove(id),
    onSuccess: () => { setRemoving(null); void refresh(); },
    onError,
  });

  if (nodes.length === 0) return null;

  return (
    <section className="border-t border-white/10 pt-6">
      <h2 className="mb-1 text-2xl font-bold text-white">{t('edgeNodes.title')}</h2>
      <p className="mb-4 text-sm text-gray-400">{t('edgeNodes.description')}</p>
      <ul className="space-y-3">
        {nodes.map((node) => (
          <li key={node.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-white/10 bg-white/5 p-4">
            <Router className="h-5 w-5 shrink-0 text-cyan-300" />
            <div className="min-w-0 flex-1">
              {renaming?.id === node.id ? (
                <form
                  className="flex flex-wrap items-center gap-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const name = renaming.name.trim();
                    if (name) rename.mutate({ id: node.id, name });
                  }}
                >
                  <input
                    autoFocus
                    value={renaming.name}
                    maxLength={100}
                    aria-label={t('edgeNodes.name')}
                    onChange={(event) => setRenaming({ id: node.id, name: event.target.value })}
                    className="min-w-0 flex-1 rounded-lg border border-white/15 bg-black/30 px-3 py-1.5 text-sm text-white"
                  />
                  <button type="submit" disabled={rename.isPending} aria-label={t('common.save')} className="rounded-lg p-2 text-emerald-300 hover:bg-white/10">
                    <Check className="h-4 w-4" />
                  </button>
                  <button type="button" onClick={() => setRenaming(null)} aria-label={t('common.cancel')} className="rounded-lg p-2 text-gray-300 hover:bg-white/10">
                    <X className="h-4 w-4" />
                  </button>
                </form>
              ) : (
                <p className="truncate font-medium text-white">{node.name}</p>
              )}
              <p className="text-xs text-gray-400">
                {t(`edgeNodes.kinds.${node.kind}`)}
                {node.runtime_version && ` · ${node.runtime_version}`}
                {node.last_seen_at && ` · ${t('edgeNodes.lastContact', { date: formatDateTime(node.last_seen_at) })}`}
              </p>
            </div>
            <span className={`rounded-full px-3 py-0.5 text-xs font-semibold ${
              node.online ? 'bg-emerald-400/15 text-emerald-200' : 'bg-white/10 text-gray-300'
            }`}>
              {t(node.online ? 'edgeNodes.online' : 'edgeNodes.offline')}
            </span>
            {renaming?.id !== node.id && (
              <div className="flex gap-1">
                <button type="button" onClick={() => setRenaming({ id: node.id, name: node.name })} aria-label={t('edgeNodes.rename')} className="rounded-lg p-2 text-gray-300 hover:bg-white/10 hover:text-white">
                  <Pencil className="h-4 w-4" />
                </button>
                <button type="button" onClick={() => setRemoving(node)} aria-label={t('edgeNodes.remove')} className="rounded-lg p-2 text-gray-300 hover:bg-white/10 hover:text-red-300">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
      <ConfirmDeleteModal
        isOpen={removing !== null}
        onClose={() => setRemoving(null)}
        onConfirm={() => removing && remove.mutate(removing.id)}
        isLoading={remove.isPending}
        title={t('edgeNodes.remove')}
        message={t('edgeNodes.removeWarning')}
        itemName={removing?.name}
      />
    </section>
  );
}
