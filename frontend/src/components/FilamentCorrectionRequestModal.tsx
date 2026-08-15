import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Loader2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { AxiosError } from 'axios';

import { filamentsAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { ModalOverlay } from './ModalOverlay';

interface FilamentCorrectionRequestModalProps {
  filamentId: number;
  isOpen: boolean;
  onClose: () => void;
  onSent: () => void;
}

export const FilamentCorrectionRequestModal: React.FC<FilamentCorrectionRequestModalProps> = ({
  filamentId,
  isOpen,
  onClose,
  onSent,
}) => {
  const { t } = useTranslation();
  const [message, setMessage] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) setError(null);
  }, [isOpen]);

  const mutation = useMutation({
    mutationFn: () => filamentsAPI.requestCommonEdit(filamentId, message.trim()),
    onSuccess: ({ recipients }) => {
      if (recipients === 0) {
        setError(t('createFilament.commonEditRequestNoRecipients'));
        return;
      }
      setMessage('');
      setError(null);
      onSent();
      onClose();
    },
    onError: (requestError: AxiosError<{ detail: unknown }>) => {
      setError(translateApiError(
        t,
        requestError.response?.data?.detail,
        t('createFilament.commonEditRequestFailed'),
      ));
    },
  });

  if (!isOpen) return null;

  return (
    <ModalOverlay
      onClose={() => {
        if (!mutation.isPending) onClose();
      }}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
        className="w-full max-w-lg rounded-2xl border border-white/20 bg-gray-900 p-6 shadow-2xl"
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-xl font-bold text-white">
              {t('createFilament.commonEditRequestTitle')}
            </h3>
            <p className="mt-2 text-sm leading-6 text-gray-400">
              {t('createFilament.commonEditRequestDescription')}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={mutation.isPending}
            className="rounded-lg p-2 text-gray-400 transition hover:bg-white/10 hover:text-white"
            aria-label={t('createFilament.commonEditRequestCancel')}
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <textarea
          autoFocus
          required
          minLength={5}
          maxLength={1000}
          rows={5}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={t('createFilament.commonEditRequestPlaceholder')}
          className="w-full resize-y rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-white placeholder-gray-500 outline-none focus:ring-2 focus:ring-cyan-500"
        />
        {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
        <div className="mt-5 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={mutation.isPending}
            className="rounded-xl bg-white/10 px-4 py-2.5 text-white transition hover:bg-white/20"
          >
            {t('createFilament.commonEditRequestCancel')}
          </button>
          <button
            type="submit"
            disabled={mutation.isPending || message.trim().length < 5}
            className="flex items-center gap-2 rounded-xl bg-cyan-600 px-4 py-2.5 text-white transition hover:bg-cyan-700 disabled:opacity-50"
          >
            {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {t(mutation.isPending
              ? 'createFilament.commonEditRequestSending'
              : 'createFilament.commonEditRequestSend')}
          </button>
        </div>
      </form>
    </ModalOverlay>
  );
};
