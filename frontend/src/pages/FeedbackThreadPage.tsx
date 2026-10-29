import { ArrowLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { FeedbackThreadView } from '../components/FeedbackThreadView';

export function FeedbackThreadPage() {
  const { feedbackId } = useParams();
  const parsedFeedbackId = Number(feedbackId);
  const navigate = useNavigate();
  const { t } = useTranslation();

  if (!Number.isInteger(parsedFeedbackId) || parsedFeedbackId <= 0) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 text-center text-red-200">
        {t('feedbackThread.notFound')}
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-3 py-6 sm:px-6 sm:py-10">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="mb-4 inline-flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-slate-300 transition-colors hover:bg-white/5 hover:text-white"
      >
        <ArrowLeft className="h-4 w-4" />
        {t('feedbackThread.back')}
      </button>
      <FeedbackThreadView feedbackId={parsedFeedbackId} />
    </div>
  );
}
