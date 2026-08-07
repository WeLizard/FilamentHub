/** Компонент для управления материалами каталога в админке */

import { lazy, Suspense, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Edit, Trash2, Eye, EyeOff, Layers, Loader2 } from 'lucide-react';
import { filamentsAPI } from '../../api/client';
import { FilamentPreview } from '../FilamentPreview';
import { ConfirmDeleteModal } from '../ConfirmDeleteModal';
import { toast } from '../Toast';
import { translateApiError } from '../../utils/translateApiError';
import { useDebounce } from '../../hooks/useDebounce';
import type { Filament } from '../../types/api';
import type { AxiosError } from 'axios';

const CreateFilamentModal = lazy(() =>
  import('../CreateFilamentModal').then((m) => ({ default: m.CreateFilamentModal }))
);

const PAGE_SIZE = 20;

export function AdminMaterials() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [showOffShelf, setShowOffShelf] = useState(true);
  const [editingFilament, setEditingFilament] = useState<Filament | null>(null);
  const [deletingFilament, setDeletingFilament] = useState<Filament | null>(null);
  const debouncedSearch = useDebounce(searchQuery, 300);

  const { data, isLoading } = useQuery({
    queryKey: ['admin-materials', page, debouncedSearch, showOffShelf],
    queryFn: () =>
      filamentsAPI.list({
        page,
        size: PAGE_SIZE,
        active_only: !showOffShelf,
        search: debouncedSearch || undefined,
      }),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['admin-materials'] });
    queryClient.invalidateQueries({ queryKey: ['filaments'] });
  };

  const shelfMutation = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      filamentsAPI.update(id, { active }),
    onSuccess: (_result, variables) => {
      refresh();
      toast.success(
        variables.active ? t('adminMaterials.putOnShelfDone') : t('adminMaterials.takenOffShelf')
      );
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, err.response?.data?.detail, t('adminMaterials.shelfFailed')));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => filamentsAPI.delete(id),
    onSuccess: () => {
      refresh();
      setDeletingFilament(null);
      toast.success(t('adminMaterials.deleted'));
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      toast.error(
        translateApiError(t, err.response?.data?.detail, t('adminMaterials.deleteFailed')),
        12000
      );
      setDeletingFilament(null);
    },
  });

  const materials = data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-bold text-white">
          {t('adminMaterials.title')}
          {data ? <span className="ml-2 text-sm text-gray-400">{data.total}</span> : null}
        </h2>
        <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
          <input
            type="checkbox"
            checked={showOffShelf}
            onChange={(e) => {
              setShowOffShelf(e.target.checked);
              setPage(1);
            }}
            className="accent-purple-500"
          />
          {t('adminMaterials.showOffShelf')}
        </label>
      </div>

      <input
        type="text"
        value={searchQuery}
        onChange={(e) => {
          setSearchQuery(e.target.value);
          setPage(1);
        }}
        placeholder={t('adminMaterials.searchPlaceholder')}
        className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
      />

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 text-purple-400 animate-spin" />
        </div>
      ) : materials.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Layers className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>{t('adminMaterials.nothingFound')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {materials.map((filament) => (
            <div
              key={filament.id}
              className="bg-white/5 rounded-xl p-4 border border-white/10 hover:border-white/20 transition-all"
            >
              <div className="flex items-start gap-4">
                <FilamentPreview
                  colorHex={filament.color_hex}
                  visualSettings={filament.visual_settings}
                  size="small"
                  className="shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <h3 className="text-lg font-semibold text-white break-words">{filament.name}</h3>
                    <span className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 text-xs font-semibold">
                      {filament.material_type}
                    </span>
                    {!filament.active && (
                      <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 text-xs font-semibold">
                        {t('adminMaterials.offShelf')}
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-400 flex flex-wrap gap-x-4 gap-y-1">
                    <span>{filament.brand_name}</span>
                    {filament.color_name && <span>{filament.color_name}</span>}
                    <span>
                      {t('adminMaterials.presets')}: {filament.presets_count ?? 0}
                    </span>
                    <span className="text-gray-500">#{filament.id}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => setEditingFilament(filament)}
                    className="p-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all"
                    title={t('adminMaterials.edit')}
                  >
                    <Edit className="w-5 h-5" />
                  </button>
                  <button
                    onClick={() =>
                      shelfMutation.mutate({ id: filament.id, active: !filament.active })
                    }
                    className="p-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all"
                    title={
                      filament.active
                        ? t('adminMaterials.takeOffShelf')
                        : t('adminMaterials.putOnShelf')
                    }
                  >
                    {filament.active ? (
                      <EyeOff className="w-5 h-5" />
                    ) : (
                      <Eye className="w-5 h-5" />
                    )}
                  </button>
                  <button
                    onClick={() => setDeletingFilament(filament)}
                    className="p-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg transition-all"
                    title={t('adminMaterials.delete')}
                  >
                    <Trash2 className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {data && data.pages > 1 && (
        <div className="flex items-center justify-center space-x-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-4 py-2 rounded-lg bg-white/5 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-white/10"
          >
            {t('adminMaterials.prev')}
          </button>
          <span className="text-gray-400">
            {t('adminMaterials.page')} {page} {t('adminMaterials.of')} {data.pages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
            disabled={page === data.pages}
            className="px-4 py-2 rounded-lg bg-white/5 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-white/10"
          >
            {t('adminMaterials.next')}
          </button>
        </div>
      )}

      {editingFilament && (
        <Suspense fallback={null}>
          <CreateFilamentModal
            isOpen
            filament={editingFilament}
            onClose={() => {
              setEditingFilament(null);
              refresh();
            }}
          />
        </Suspense>
      )}

      <ConfirmDeleteModal
        isOpen={deletingFilament !== null}
        onClose={() => setDeletingFilament(null)}
        onConfirm={() => deletingFilament && deleteMutation.mutate(deletingFilament.id)}
        isLoading={deleteMutation.isPending}
        itemName={deletingFilament?.name}
        title={t('adminMaterials.deleteTitle')}
        // Удаление уносит пресеты и отзывы: счётчик говорит, чего именно это стоит.
        message={t('adminMaterials.deleteMessage', {
          presets: deletingFilament?.presets_count ?? 0,
        })}
      />
    </div>
  );
}
