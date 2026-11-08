import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Loader2, Send } from 'lucide-react';

import { feedbackAPI } from '../api/client';
import { apiErrorDetail } from '../utils/apiErrorDetail';
import { translateApiError } from '../utils/translateApiError';

const MAX_WISH_LENGTH = 5000;
const EXAMPLE_KEYS = [
  'printers',
  'quotes',
  'reports',
  'team',
  'api',
  'purchaseLinks',
  'directPurchases',
] as const;

export function WorkshopWishBox() {
  const { t } = useTranslation();
  const [message, setMessage] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (draft: string) =>
      feedbackAPI.create({
        type: 'feature',
        subject: t('settings.workshopWish.subject'),
        message: draft.trim(),
        source: 'profile_workshop_tab',
      }),
    onSuccess: (_, submittedDraft) => {
      setMessage((currentDraft) => (currentDraft === submittedDraft ? '' : currentDraft));
      setSent(true);
      setError(null);
    },
    onError: (requestError: unknown) => {
      setSent(false);
      setError(
        translateApiError(
          t,
          apiErrorDetail(requestError),
          t('settings.workshopWish.error'),
        ),
      );
    },
  });

  const trimmed = message.trim();
  const submit = () => {
    if (!trimmed || mutation.isPending) return;
    setSent(false);
    mutation.mutate(message);
  };

  return (
    <section className="rounded-[1.75rem] border border-white/10 bg-slate-950/55 p-5 shadow-2xl shadow-black/20 md:p-6">
      <h3 className="text-lg font-bold text-white">
        {t('settings.workshopWish.title')}
      </h3>
      <p className="mt-1 text-sm leading-6 text-gray-300">
        {t('settings.workshopWish.intro')}
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLE_KEYS.map((key) => (
          <span
            key={key}
            className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-gray-300"
          >
            {t(`settings.workshopWish.examples.${key}`)}
          </span>
        ))}
      </div>
      <p className="mt-3 text-xs leading-5 text-gray-500">
        {t('settings.workshopWish.footnote')}
      </p>

      <label htmlFor="workshop-wish" className="mt-4 block text-xs text-gray-400">
        {t('settings.workshopWish.label')}
      </label>
      <textarea
        id="workshop-wish"
        value={message}
        maxLength={MAX_WISH_LENGTH}
        rows={4}
        placeholder={t('settings.workshopWish.placeholder')}
        onChange={(event) => {
          setMessage(event.target.value);
          setSent(false);
          setError(null);
        }}
        className="mt-1.5 w-full rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-sm text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-cyan-400/40"
      />

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={submit}
          disabled={!trimmed || mutation.isPending}
          className="inline-flex items-center gap-2 rounded-xl border border-cyan-400/30 bg-cyan-400/10 px-4 py-2.5 text-sm font-medium text-cyan-50 transition hover:bg-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {mutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
          {mutation.isPending
            ? t('settings.workshopWish.sending')
            : t('settings.workshopWish.submit')}
        </button>
        <span className="text-xs text-gray-500">
          {t('settings.workshopWish.counter', {
            count: message.length,
            max: MAX_WISH_LENGTH,
          })}
        </span>
      </div>

      <div aria-live="polite" className="mt-3">
        {sent && (
          <p className="text-sm text-green-200">
            {t('settings.workshopWish.success')}
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-red-300">
            {error}
          </p>
        )}
      </div>
    </section>
  );
}
