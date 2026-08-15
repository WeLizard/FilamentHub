import { ExternalLink, ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const OFFICIAL_SAFETY_REFERENCE_URLS: Record<string, string> = {
  ru: 'https://protect.gost.ru/gost/details/c4ca13fd-c6ba-4707-bc0a-0aa53cb4a22c',
  en: 'https://unece.org/transport/documents/2025/09/standards/globally-harmonized-system-classification-and-labelling',
  zh: 'https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=67992CA972A4CF9222095CA06064724A',
};

export function chemicalSafetyReferenceUrl(language: string): string {
  const locale = language.split('-')[0];
  return OFFICIAL_SAFETY_REFERENCE_URLS[locale] ?? OFFICIAL_SAFETY_REFERENCE_URLS.en;
}

export function ChemicalSafetyNotice() {
  const { t, i18n } = useTranslation();
  const referenceUrl = chemicalSafetyReferenceUrl(
    i18n.resolvedLanguage || i18n.language || 'en',
  );

  return (
    <div className="mt-3 flex gap-2 rounded-xl border border-amber-400/25 bg-amber-500/10 p-3 text-xs leading-5 text-amber-100">
      <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <p>{t('filamentHandling.chemicalSafetyNotice')}</p>
        <a
          href={referenceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-1.5 inline-flex items-center gap-1 font-medium text-amber-50 underline decoration-amber-300/50 underline-offset-2 hover:text-white"
        >
          {t('filamentHandling.chemicalSafetyReference')}
          <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    </div>
  );
}
