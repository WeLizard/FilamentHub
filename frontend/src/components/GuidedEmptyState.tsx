import type { ReactNode } from 'react';
import { ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

interface GuidedEmptyStateProps {
  icon: ReactNode;
  eyebrow: string;
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
  guideLabel: string;
  guideTo: string;
}

export function GuidedEmptyState({
  icon,
  eyebrow,
  title,
  description,
  actionLabel,
  onAction,
  guideLabel,
  guideTo,
}: GuidedEmptyStateProps) {
  const { i18n } = useTranslation();
  const language = (i18n.resolvedLanguage || i18n.language).split('-')[0];
  const availableGuideTo = language === 'ru' ? guideTo : '/wiki';

  return (
    <div className="rounded-2xl border border-cyan-300/15 bg-gradient-to-br from-white/[0.055] via-white/[0.035] to-cyan-400/[0.045] p-5 text-left shadow-lg shadow-black/10 sm:p-6">
      <div className="flex items-start gap-4">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-cyan-300/15 bg-cyan-300/10 text-cyan-200">
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-gray-500">{eyebrow}</p>
          <h3 className="mt-2 text-base font-semibold text-white sm:text-lg">{title}</h3>
          <p className="mt-1.5 max-w-2xl text-sm leading-6 text-gray-300">{description}</p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onAction}
              className="inline-flex items-center justify-center rounded-xl border border-white/15 bg-white/8 px-4 py-2 text-sm font-semibold text-white transition hover:border-cyan-300/25 hover:bg-white/12"
            >
              {actionLabel}
            </button>
            <Link
              to={availableGuideTo}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-cyan-300 transition hover:text-cyan-200"
            >
              {guideLabel}
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
