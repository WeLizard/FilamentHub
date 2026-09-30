import { AlertTriangle, CheckCircle2, CircleDashed, Settings2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type {
  EconomicsReadiness,
  EconomicsReadinessReason,
  EconomicsReadinessStatus,
} from '../../types/api';
import {
  ECONOMICS_FIELD_I18N_KEYS,
  INFORMATIONAL_ECONOMICS_REASONS,
  worstEconomicsReadinessStatus,
} from '../../utils/economicsReadiness';

export interface EconomicsReadinessEntry {
  id: string;
  label: string;
  readiness: EconomicsReadiness | null;
}

interface EconomicsReadinessPanelProps {
  entries: EconomicsReadinessEntry[];
  isLoading?: boolean;
  error?: boolean;
  onConfigure?: () => void;
}

const toneClasses: Record<EconomicsReadinessStatus, string> = {
  configured: 'border-emerald-400/20 bg-emerald-500/[0.07]',
  partial: 'border-amber-400/25 bg-amber-500/[0.08]',
  incomplete: 'border-amber-400/25 bg-amber-500/[0.08]',
};

const configureButtonClass =
  'inline-flex shrink-0 self-start items-center gap-2 rounded-xl border border-white/10 bg-white/[0.07] px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-white/10';

export const EconomicsReadinessPanel: React.FC<EconomicsReadinessPanelProps> = ({
  entries,
  isLoading = false,
  error = false,
  onConfigure,
}) => {
  const { t } = useTranslation();
  const knownEntries = entries.filter(
    (entry): entry is EconomicsReadinessEntry & { readiness: EconomicsReadiness } => Boolean(entry.readiness),
  );
  const status = worstEconomicsReadinessStatus(knownEntries.map((entry) => entry.readiness));

  if (isLoading && status == null) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-2" role="status">
        <span className="flex items-center gap-2 text-xs text-slate-300">
          <CircleDashed className="h-3.5 w-3.5 animate-spin text-slate-400" />
          {t('printerCost.readiness.loading')}
        </span>
      </div>
    );
  }

  if (error || status == null) {
    return (
      <div className="rounded-2xl border border-amber-400/20 bg-amber-500/[0.06] px-3 py-2" role="status">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex items-start gap-2 text-xs leading-5 text-amber-100">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-300" />
            {t('printerCost.readiness.unavailable')}
          </span>
          {onConfigure ? (
            <button type="button" onClick={onConfigure} className={configureButtonClass}>
              <Settings2 className="h-3.5 w-3.5" />
              {t('printerCost.readiness.configure')}
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  if (status === 'configured') {
    return (
      <div className={`rounded-2xl border px-3 py-2 ${toneClasses.configured}`} role="status">
        <span className="flex items-center gap-2 text-xs font-semibold text-emerald-100">
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-300" />
          {t('printerCost.readiness.status.configured.title')}
        </span>
      </div>
    );
  }

  const problems = knownEntries
    .filter((entry) => entry.readiness.status !== 'configured')
    .map((entry) => {
      const fieldProblems = entry.readiness.required_fields
        .filter((field) => !field.usable)
        .map((field) => {
          const name = t(ECONOMICS_FIELD_I18N_KEYS[field.key]);
          return field.missing_reason && field.missing_reason !== 'missing' && field.missing_reason !== 'missing_currency'
            ? `${name} — ${t(`printerCost.readiness.reasons.${field.missing_reason}`)}`
            : name;
        });
      const fieldReasons = new Set<EconomicsReadinessReason>(
        entry.readiness.required_fields.flatMap((field) => (
          field.missing_reason ? [field.missing_reason] : []
        )),
      );
      const otherProblems = entry.readiness.reasons
        .filter((reason) => !fieldReasons.has(reason) && !INFORMATIONAL_ECONOMICS_REASONS.has(reason))
        .map((reason) => t(`printerCost.readiness.reasons.${reason}`));
      return { id: entry.id, label: entry.label, items: [...fieldProblems, ...otherProblems] };
    })
    .filter((problem) => problem.items.length > 0);

  return (
    <div className={`rounded-2xl border px-3 py-2 ${toneClasses[status]}`} role="status">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-xs font-semibold text-amber-100">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-300" />
            {t(`printerCost.readiness.status.${status}.title`)}
          </p>
          {problems.length > 0 ? (
            <ul className="mt-1 space-y-0.5 pl-[1.375rem] text-[11px] leading-4 text-slate-300">
              {problems.map((problem) => (
                <li key={problem.id}>
                  {entries.length > 1 ? <span className="text-slate-400">{problem.label}: </span> : null}
                  {problem.items.join(', ')}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        {onConfigure ? (
          <button type="button" onClick={onConfigure} className={configureButtonClass}>
            <Settings2 className="h-3.5 w-3.5" />
            {t('printerCost.readiness.configure')}
          </button>
        ) : null}
      </div>
    </div>
  );
};
