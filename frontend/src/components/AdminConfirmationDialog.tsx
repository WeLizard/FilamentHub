import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { AlertTriangle, Loader2, Mail, ShieldCheck, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { AxiosError } from 'axios';
import type { AdminReauthChallenge, AdminReauthConfirmation } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { ModalOverlay } from './ModalOverlay';

interface AdminConfirmationDialogProps {
  isOpen: boolean;
  challengeKey: string;
  title: string;
  message: string;
  confirmText: string;
  requestChallenge: () => Promise<AdminReauthChallenge>;
  onConfirm: (confirmation: AdminReauthConfirmation) => Promise<unknown>;
  onClose: () => void;
  variant?: 'danger' | 'warning';
  icon?: ReactNode;
}

export function AdminConfirmationDialog({
  isOpen,
  challengeKey,
  title,
  message,
  confirmText,
  requestChallenge,
  onConfirm,
  onClose,
  variant = 'warning',
  icon,
}: AdminConfirmationDialogProps) {
  const { t, i18n } = useTranslation();
  const [challenge, setChallenge] = useState<AdminReauthChallenge | null>(null);
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isRequesting, setIsRequesting] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const operationRef = useRef(0);

  useEffect(() => {
    operationRef.current += 1;
    setChallenge(null);
    setCode('');
    setError(null);
    setIsRequesting(false);
    setIsConfirming(false);
  }, [isOpen, challengeKey]);

  if (!isOpen) return null;

  const translateError = (caught: unknown) => {
    const detail = (caught as AxiosError<{ detail?: unknown }>)?.response?.data?.detail;
    return translateApiError(t, detail, t('adminConfirmation.errorFallback'));
  };

  const handleRequest = async () => {
    const operation = ++operationRef.current;
    setIsRequesting(true);
    setChallenge(null);
    setCode('');
    setError(null);
    try {
      const nextChallenge = await requestChallenge();
      if (operation !== operationRef.current) return;
      setChallenge(nextChallenge);
      setCode('');
    } catch (caught) {
      if (operation === operationRef.current) setError(translateError(caught));
    } finally {
      if (operation === operationRef.current) setIsRequesting(false);
    }
  };

  const handleConfirm = async (event: FormEvent) => {
    event.preventDefault();
    if (isRequesting || isConfirming || !challenge || !/^\d{6}$/.test(code)) return;
    const operation = ++operationRef.current;
    setIsConfirming(true);
    setError(null);
    try {
      await onConfirm({ challenge_id: challenge.challenge_id, code });
      if (operation === operationRef.current) onClose();
    } catch (caught) {
      if (operation === operationRef.current) setError(translateError(caught));
    } finally {
      if (operation === operationRef.current) setIsConfirming(false);
    }
  };

  const handleClose = () => {
    if (isConfirming) return;
    operationRef.current += 1;
    onClose();
  };

  const expiresAt = challenge
    ? new Intl.DateTimeFormat(i18n.language, { hour: '2-digit', minute: '2-digit' })
      .format(new Date(challenge.expires_at))
    : null;
  const danger = variant === 'danger';

  return (
    <ModalOverlay onClose={handleClose} closeOnOverlayClick={!isConfirming}>
      <div
        className="w-full max-w-md overflow-hidden rounded-2xl border border-white/20 bg-gradient-to-br from-purple-900 to-indigo-900 shadow-xl"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-confirmation-title"
      >
        <div className="flex items-center justify-between gap-4 border-b border-white/10 p-5 sm:p-6">
          <div className="flex min-w-0 items-center gap-3">
            <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg ${danger ? 'bg-red-500/20 text-red-300' : 'bg-amber-500/20 text-amber-200'}`}>
              {icon ?? (danger ? <AlertTriangle className="h-5 w-5" /> : <ShieldCheck className="h-5 w-5" />)}
            </div>
            <h2 id="admin-confirmation-title" className="text-lg font-bold text-white sm:text-xl">
              {title}
            </h2>
          </div>
          <button
            type="button"
            onClick={handleClose}
            disabled={isConfirming}
            className="shrink-0 rounded-lg p-2 text-gray-400 transition hover:bg-white/10 hover:text-white disabled:opacity-50"
            aria-label={t('common.close')}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleConfirm} className="space-y-5 p-5 sm:p-6">
          <p className="text-sm leading-6 text-gray-300">{message}</p>

          {challenge ? (
            <div className="space-y-3">
              <div className="rounded-xl border border-blue-400/20 bg-blue-400/10 p-3 text-sm text-blue-100">
                <div className="flex items-start gap-2">
                  <Mail className="mt-0.5 h-4 w-4 shrink-0" />
                  <p>{t('adminConfirmation.sentTo', { email: challenge.masked_email })}</p>
                </div>
                <p className="mt-1 pl-6 text-xs text-blue-200/75">
                  {t('adminConfirmation.expiresAt', { time: expiresAt })}
                </p>
              </div>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-gray-200">
                  {t('adminConfirmation.codeLabel')}
                </span>
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  value={code}
                  onChange={(event) => {
                    setCode(event.target.value.replace(/\D/g, '').slice(0, 6));
                    setError(null);
                  }}
                  autoFocus
                  className="w-40 rounded-lg border border-white/20 bg-white/10 px-3 py-2 text-center font-mono text-lg tracking-[0.3em] text-white outline-none transition focus:border-purple-400/50 focus:ring-2 focus:ring-purple-500/25"
                  aria-describedby="admin-confirmation-code-hint"
                />
                <span id="admin-confirmation-code-hint" className="mt-1.5 block text-xs text-gray-400">
                  {t('adminConfirmation.codeHint')}
                </span>
              </label>
            </div>
          ) : (
            <p className="text-sm text-gray-400">{t('adminConfirmation.sendHint')}</p>
          )}

          {error && (
            <p className="text-sm text-red-300" role="alert">{error}</p>
          )}

          <div className="flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={handleClose}
              disabled={isConfirming}
              className="rounded-xl bg-white/10 px-4 py-2.5 text-sm text-white transition hover:bg-white/20 disabled:opacity-50"
            >
              {t('common.cancel')}
            </button>
            {challenge && (
              <button
                type="button"
                onClick={handleRequest}
                disabled={isRequesting || isConfirming}
                className="rounded-xl border border-white/15 px-4 py-2.5 text-sm text-gray-200 transition hover:bg-white/10 disabled:opacity-50"
              >
                {isRequesting ? t('adminConfirmation.sending') : t('adminConfirmation.resend')}
              </button>
            )}
            <button
              type={challenge ? 'submit' : 'button'}
              onClick={challenge ? undefined : handleRequest}
              disabled={isRequesting || isConfirming || (challenge !== null && !/^\d{6}$/.test(code))}
              className={`inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-50 ${danger ? 'bg-red-600 hover:bg-red-700' : 'bg-amber-600 hover:bg-amber-700'}`}
            >
              {(isRequesting || isConfirming) && <Loader2 className="h-4 w-4 animate-spin" />}
              {challenge
                ? (isConfirming ? t('adminConfirmation.confirming') : confirmText)
                : (isRequesting ? t('adminConfirmation.sending') : t('adminConfirmation.sendCode'))}
            </button>
          </div>
        </form>
      </div>
    </ModalOverlay>
  );
}
