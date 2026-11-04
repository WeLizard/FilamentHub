import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getProtectedImageBlob } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

export function useProtectedImage(src: string) {
  const { user } = useAuth();
  const account = user?.id;
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{
    src: string; account: typeof account; attempt: number;
    status: 'loading' | 'ready' | 'error'; objectUrl: string | null;
  } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    const identity = { src, account, attempt };
    setState({ ...identity, status: 'loading', objectUrl: null });
    void getProtectedImageBlob(src, controller.signal).then((blob) => {
      if (controller.signal.aborted) return;
      objectUrl = URL.createObjectURL(blob);
      setState({ ...identity, status: 'loading', objectUrl });
    }).catch(() => {
      if (!controller.signal.aborted) setState({ ...identity, status: 'error', objectUrl: null });
    });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src, account, attempt]);

  const current = state?.src === src && state.account === account && state.attempt === attempt ? state : null;
  const finish = (status: 'ready' | 'error') => {
    setState((previous) => previous && previous === current ? { ...previous, status } : previous);
  };
  return {
    status: current?.status ?? 'loading',
    objectUrl: current?.status === 'error' ? null : current?.objectUrl ?? null,
    retry: () => setAttempt((value) => value + 1),
    onLoad: () => finish('ready'),
    onError: () => finish('error'),
  };
}

export function ProtectedImageError({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex max-w-full flex-wrap items-center gap-2 rounded-lg border border-white/10 bg-black/20 p-3 text-sm">
      <span role="status">{t('protectedImage.error')}</span>
      <button type="button" onClick={onRetry} className="rounded-lg border border-white/20 px-3 py-2 hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-purple-500">
        {t('protectedImage.retry')}
      </button>
    </span>
  );
}
