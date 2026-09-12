import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Loader2, Mail, ShieldCheck, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { AxiosError } from 'axios';
import { authAPI, type AccountEmailChangeChallenge } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { ModalOverlay } from './ModalOverlay';

interface AccountEmailChangeDialogProps {
  isOpen: boolean;
  newEmail: string;
  onComplete: () => void;
  onClose: () => void;
}

export function AccountEmailChangeDialog({
  isOpen,
  newEmail,
  onComplete,
  onClose,
}: AccountEmailChangeDialogProps) {
  const { t, i18n } = useTranslation();
  const [challenge, setChallenge] = useState<AccountEmailChangeChallenge | null>(null);
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
  }, [isOpen, newEmail]);

  if (!isOpen) return null;

  const translateError = (caught: unknown) => {
    const detail = (caught as AxiosError<{ detail?: unknown }>)?.response?.data?.detail;
    return translateApiError(t, detail, t('emailChangeConfirmation.errorFallback'));
  };

  const requestChallenge = async () => {
    const operation = ++operationRef.current;
    setIsRequesting(true);
    setChallenge(null);
    setCode('');
    setError(null);
    try {
      const nextChallenge = await authAPI.createEmailChangeChallenge(newEmail);
      if (operation !== operationRef.current) return;
      setChallenge(nextChallenge);
    } catch (caught) {
      if (operation === operationRef.current) setError(translateError(caught));
    } finally {
      if (operation === operationRef.current) setIsRequesting(false);
    }
  };

  const confirmChange = async (event: FormEvent) => {
    event.preventDefault();
    if (!challenge || !/^\d{6}$/.test(code) || isRequesting || isConfirming) return;
    const operation = ++operationRef.current;
    setIsConfirming(true);
    setError(null);
    try {
      await authAPI.updateEmail({
        new_email: newEmail,
        confirmation: { challenge_id: challenge.challenge_id, code },
      });
      if (operation !== operationRef.current) return;
      onComplete();
      onClose();
    } catch (caught) {
      if (operation === operationRef.current) setError(translateError(caught));
    } finally {
      if (operation === operationRef.current) setIsConfirming(false);
    }
  };

  const close = () => {
    if (isConfirming) return;
    operationRef.current += 1;
    onClose();
  };

  const expiresAt = challenge
    ? new Intl.DateTimeFormat(i18n.language, { hour: '2-digit', minute: '2-digit' })
      .format(new Date(challenge.expires_at))
    : null;

  return (
    <ModalOverlay onClose={close} closeOnOverlayClick={!isConfirming}>
      <div
        className="w-full max-w-md overflow-hidden rounded-2xl border border-white/20 bg-gradient-to-br from-purple-900 to-indigo-900 shadow-xl"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-email-change-title"
      >
        <div className="flex items-center justify-between gap-4 border-b border-white/10 p-5 sm:p-6">
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-blue-500/20 text-blue-200">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <h2 id="account-email-change-title" className="text-lg font-bold text-white sm:text-xl">
              {t('emailChangeConfirmation.title')}
            </h2>
          </div>
          <button
            type="button"
            onClick={close}
            disabled={isConfirming}
            className="shrink-0 rounded-lg p-2 text-gray-400 transition hover:bg-white/10 hover:text-white disabled:opacity-50"
            aria-label={t('common.close')}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={confirmChange} className="space-y-5 p-5 sm:p-6">
          <p className="text-sm leading-6 text-gray-300">
            {t('emailChangeConfirmation.message', { email: newEmail })}
          </p>
          {challenge ? (
            <div className="space-y-3">
              <div className="rounded-xl border border-blue-400/20 bg-blue-400/10 p-3 text-sm text-blue-100">
                <div className="flex items-start gap-2">
                  <Mail className="mt-0.5 h-4 w-4 shrink-0" />
                  <p>{t('emailChangeConfirmation.sentTo', { email: challenge.masked_email })}</p>
                </div>
                <p className="mt-1 pl-6 text-xs text-blue-200/75">
                  {t('emailChangeConfirmation.expiresAt', { time: expiresAt })}
                </p>
              </div>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-gray-200">
                  {t('emailChangeConfirmation.codeLabel')}
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
                />
              </label>
            </div>
          ) : (
            <p className="text-sm text-gray-400">{t('emailChangeConfirmation.sendHint')}</p>
          )}
          {error && <p className="text-sm text-red-300" role="alert">{error}</p>}
          <div className="flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={close}
              disabled={isConfirming}
              className="rounded-xl bg-white/10 px-4 py-2.5 text-sm text-white transition hover:bg-white/20 disabled:opacity-50"
            >
              {t('common.cancel')}
            </button>
            {challenge && (
              <button
                type="button"
                onClick={requestChallenge}
                disabled={isRequesting || isConfirming}
                className="rounded-xl border border-white/15 px-4 py-2.5 text-sm text-gray-200 transition hover:bg-white/10 disabled:opacity-50"
              >
                {isRequesting ? t('emailChangeConfirmation.sending') : t('emailChangeConfirmation.resend')}
              </button>
            )}
            <button
              type={challenge ? 'submit' : 'button'}
              onClick={challenge ? undefined : requestChallenge}
              disabled={isRequesting || isConfirming || (challenge !== null && !/^\d{6}$/.test(code))}
              className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {(isRequesting || isConfirming) && <Loader2 className="h-4 w-4 animate-spin" />}
              {challenge
                ? (isConfirming ? t('emailChangeConfirmation.confirming') : t('emailChangeConfirmation.continue'))
                : (isRequesting ? t('emailChangeConfirmation.sending') : t('emailChangeConfirmation.sendCode'))}
            </button>
          </div>
        </form>
      </div>
    </ModalOverlay>
  );
}
