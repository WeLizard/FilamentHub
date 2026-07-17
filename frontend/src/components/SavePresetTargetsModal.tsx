/** Модалка «Добавить в Orca»: при сохранении пресета выбрать целевые принтер-профили */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, Loader2 } from 'lucide-react';
import { ModalOverlay } from './ModalOverlay';
import { toast } from './Toast';
import { savedPresetsAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { notifyProfileChanged } from '../utils/pluginBridge';
import { useAuth } from '../contexts/AuthContext';
import type { PrinterProfile } from '../types/api';
import type { AxiosError } from 'axios';

interface SavePresetTargetsModalProps {
  presetId: number | null; // null — модалка закрыта
  presetName?: string;
  profiles: PrinterProfile[]; // активные профили пользователя (2+, иначе модалку не открывать)
  onClose: () => void;
  onSaved?: () => void;
}

export const SavePresetTargetsModal: React.FC<SavePresetTargetsModalProps> = ({
  presetId,
  presetName,
  profiles,
  onClose,
  onSaved,
}) => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  const saveMutation = useMutation({
    mutationFn: async (targetIds: number[]) => {
      await savedPresetsAPI.save(presetId!);
      if (targetIds.length > 0) {
        await savedPresetsAPI.updateScope(presetId!, targetIds);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-presets'] });
      queryClient.invalidateQueries({ queryKey: ['saved-presets-details'] });
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
      queryClient.invalidateQueries({ queryKey: ['presets-stats'] });
      notifyProfileChanged();
      setSelectedIds([]);
      onSaved?.();
      onClose();
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, error?.response?.data?.detail, t('presetScope.saveError')));
    },
  });

  if (presetId === null || !user) return null;

  const toggle = (profileId: number) => {
    setSelectedIds(prev =>
      prev.includes(profileId) ? prev.filter(id => id !== profileId) : [...prev, profileId]
    );
  };

  const handleClose = () => {
    if (saveMutation.isPending) return;
    setSelectedIds([]);
    onClose();
  };

  return (
    <ModalOverlay onClose={handleClose}>
      <div className="bg-gray-900 rounded-2xl p-6 border border-white/20 max-w-md w-full">
        <h3 className="text-lg font-semibold text-white mb-1">{t('presetScope.saveTitle')}</h3>
        {presetName && (
          <p className="text-sm text-gray-400 mb-3 truncate" title={presetName}>{presetName}</p>
        )}
        <p className="text-sm text-gray-300 mb-3">{t('presetScope.saveHint')}</p>

        <div className="max-h-56 overflow-y-auto rounded-xl border border-white/10 divide-y divide-white/5 mb-4">
          {profiles.map(profile => {
            const checked = selectedIds.includes(profile.id);
            return (
              <button
                key={profile.id}
                type="button"
                onClick={() => toggle(profile.id)}
                className="w-full px-4 py-2.5 text-left text-sm text-white hover:bg-white/10 transition-all flex items-center justify-between gap-2"
              >
                <span className="truncate">{profile.name}</span>
                {checked && <Check className="w-4 h-4 text-purple-400 flex-shrink-0" />}
              </button>
            );
          })}
        </div>

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => saveMutation.mutate([])}
            disabled={saveMutation.isPending}
            className="px-4 py-2 rounded-xl text-sm text-gray-300 bg-white/10 hover:bg-white/20 transition-all disabled:opacity-50"
          >
            {t('presetScope.allPrinters')}
          </button>
          <button
            type="button"
            onClick={() => saveMutation.mutate(selectedIds)}
            disabled={saveMutation.isPending || selectedIds.length === 0}
            className="px-4 py-2 rounded-xl text-sm text-white bg-purple-600 hover:bg-purple-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {saveMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
            {t('presetScope.saveForSelected', { count: selectedIds.length })}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
};
