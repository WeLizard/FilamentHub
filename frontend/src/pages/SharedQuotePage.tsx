/** Публичная страница расшаренного коммерческого предложения (КП). */

import { useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Loader2, FileText, Calculator, AlertTriangle, Clock } from 'lucide-react';

type QuoteStatus = 'loading' | 'ok' | 'notfound' | 'expired' | 'error';

export const SharedQuotePage: React.FC = () => {
  const { uuid } = useParams<{ uuid: string }>();
  const { t } = useTranslation();
  const [status, setStatus] = useState<QuoteStatus>('loading');
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Загружаем на том же origin — CSP отдаёт backend (скрипты запрещены).
  const quoteUrl = `/api/v1/calculator/quote/${uuid}`;

  useEffect(() => {
    let cancelled = false;
    setStatus('loading');
    fetch(quoteUrl)
      .then((res) => {
        if (cancelled) return;
        if (res.ok) setStatus('ok');
        else if (res.status === 410) setStatus('expired');
        else if (res.status === 404) setStatus('notfound');
        else setStatus('error');
      })
      .catch(() => {
        if (!cancelled) setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [quoteUrl]);

  // Подгоняем высоту iframe под контент (same-origin — доступ разрешён).
  const handleIframeLoad = () => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    try {
      const height = iframe.contentDocument?.body?.scrollHeight;
      if (height) iframe.style.height = `${height + 32}px`;
    } catch {
      // ignore — оставляем min-height по умолчанию
    }
  };

  const CreateOwnCta = () => (
    <div className="mt-6 bg-white/5 border border-white/10 rounded-2xl p-5 sm:p-6 flex flex-col sm:flex-row sm:items-center gap-4">
      <Calculator className="w-8 h-8 text-purple-300 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-white font-semibold">{t('sharedQuotePage.ctaTitle')}</p>
        <p className="text-gray-400 text-sm">{t('sharedQuotePage.ctaText')}</p>
      </div>
      <Link
        to="/calculator"
        className="px-5 py-2.5 rounded-xl bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/30 text-white text-sm font-medium transition-colors text-center"
      >
        {t('sharedQuotePage.ctaButton')}
      </Link>
    </div>
  );

  if (status === 'loading') {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="w-8 h-8 text-purple-400 animate-spin" />
      </div>
    );
  }

  if (status !== 'ok') {
    const isExpired = status === 'expired';
    return (
      <div className="max-w-2xl mx-auto py-12 px-4 text-center">
        {isExpired ? (
          <Clock className="w-14 h-14 text-amber-300 mx-auto mb-4" />
        ) : (
          <AlertTriangle className="w-14 h-14 text-gray-400 mx-auto mb-4" />
        )}
        <h1 className="text-2xl font-bold text-white mb-2">
          {isExpired ? t('sharedQuotePage.expiredTitle') : t('sharedQuotePage.notFoundTitle')}
        </h1>
        <p className="text-gray-400">
          {isExpired ? t('sharedQuotePage.expiredText') : t('sharedQuotePage.notFoundText')}
        </p>
        <CreateOwnCta />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto py-6 px-4">
      <div className="flex items-center gap-2 mb-4 text-gray-300">
        <FileText className="w-5 h-5 text-purple-300" />
        <h1 className="text-lg sm:text-xl font-semibold text-white">{t('sharedQuotePage.title')}</h1>
      </div>

      <div className="bg-white rounded-2xl overflow-hidden border border-white/10 shadow-xl">
        <iframe
          ref={iframeRef}
          src={quoteUrl}
          title={t('sharedQuotePage.title')}
          onLoad={handleIframeLoad}
          className="w-full block"
          style={{ minHeight: '600px', border: 'none' }}
        />
      </div>

      <CreateOwnCta />
    </div>
  );
};
