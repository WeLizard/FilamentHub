import { AlertTriangle, CheckCircle2, ChevronDown, CircleDashed, Settings2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type {
  EconomicsReadiness,
  EconomicsReadinessReason,
  EconomicsReadinessStatus,
} from '../../types/api';
import {
  ECONOMICS_FIELD_I18N_KEYS,
  ECONOMICS_SOURCE_I18N_KEYS,
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
  partial: 'border-cyan-400/20 bg-cyan-500/[0.07]',
  incomplete: 'border-amber-400/25 bg-amber-500/[0.08]',
};

const iconClasses: Record<EconomicsReadinessStatus, string> = {
  configured: 'text-emerald-300',
  partial: 'text-cyan-300',
  incomplete: 'text-amber-300',
};

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
  const affectedNames = knownEntries
    .filter((entry) => entry.readiness.status !== 'configured')
    .map((entry) => entry.label);
  const fieldReasons = new Set<EconomicsReadinessReason>(knownEntries.flatMap((entry) => (
    entry.readiness.required_fields.flatMap((field) => (
      field.missing_reason ? [field.missing_reason] : []
    ))
  )));
  const reasons = [...new Set(knownEntries.flatMap((entry) => (
    entry.readiness.reasons.filter((reason) => !fieldReasons.has(reason))
  )))];

  if (isLoading && status == null) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3" role="status">
        <span className="flex items-center gap-2 text-sm text-slate-300">
          <CircleDashed className="h-4 w-4 animate-spin text-slate-400" />
          {t('printerCost.readiness.loading')}
        </span>
      </div>
    );
  }

  if (error || status == null) {
    return (
      <div className="rounded-2xl border border-amber-400/20 bg-amber-500/[0.06] px-4 py-3" role="status">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span className="flex items-start gap-2 text-sm leading-5 text-amber-100">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
            {t('printerCost.readiness.unavailable')}
          </span>
          {onConfigure ? (
            <button type="button" onClick={onConfigure} className="inline-flex self-start items-center gap-2 rounded-xl border border-white/10 bg-white/[0.07] px-3 py-2 text-xs font-semibold text-white transition hover:bg-white/10">
              <Settings2 className="h-3.5 w-3.5" />
              {t('printerCost.readiness.configure')}
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  const Icon = status === 'configured' ? CheckCircle2 : status === 'partial' ? CircleDashed : AlertTriangle;

  return (
    <div className={`rounded-2xl border px-4 py-3 ${toneClasses[status]}`} role="status">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-start gap-2">
            <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${iconClasses[status]}`} />
            <div>
              <p className="text-sm font-semibold text-white">
                {t(`printerCost.readiness.status.${status}.title`)}
              </p>
              <p className="mt-0.5 text-xs leading-5 text-slate-300">
                {t(`printerCost.readiness.status.${status}.description`)}
              </p>
            </div>
          </div>
          {affectedNames.length > 0 && entries.length > 1 ? (
            <p className="mt-2 text-xs leading-5 text-slate-400">
              {t('printerCost.readiness.affectedMachines', { names: affectedNames.join(', ') })}
            </p>
          ) : null}
        </div>
        {onConfigure && status !== 'configured' ? (
          <button type="button" onClick={onConfigure} className="inline-flex shrink-0 self-start items-center gap-2 rounded-xl border border-white/10 bg-white/[0.07] px-3 py-2 text-xs font-semibold text-white transition hover:bg-white/10">
            <Settings2 className="h-3.5 w-3.5" />
            {t('printerCost.readiness.configure')}
          </button>
        ) : null}
      </div>

      <details className="group mt-2.5">
        <summary className="flex w-fit cursor-pointer list-none items-center gap-1.5 text-xs font-semibold text-slate-300 marker:hidden">
          {t('printerCost.readiness.sourcesTitle')}
          <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
        </summary>
        <div className="mt-2 space-y-2 border-t border-white/10 pt-2.5">
          {knownEntries.map((entry) => (
            <div key={entry.id}>
              {entries.length > 1 ? <p className="text-xs font-semibold text-slate-200">{entry.label}</p> : null}
              <ul className={`${entries.length > 1 ? 'mt-1' : ''} grid gap-x-4 gap-y-1 sm:grid-cols-2`}>
                {entry.readiness.required_fields.map((field) => (
                  <li key={field.key} className="flex min-w-0 items-baseline justify-between gap-3 text-[11px] leading-4">
                    <span className="text-slate-400">{t(ECONOMICS_FIELD_I18N_KEYS[field.key])}</span>
                    <span className={`text-right ${field.usable ? 'text-slate-200' : 'text-amber-200'}`}>
                      {t(ECONOMICS_SOURCE_I18N_KEYS[field.source])}
                      {!field.usable && field.missing_reason
                        ? ` · ${t(`printerCost.readiness.reasons.${field.missing_reason}`)}`
                        : ''}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {reasons.length > 0 ? (
            <div className="border-t border-white/10 pt-2">
              <p className="text-[11px] font-semibold text-slate-300">
                {t('printerCost.readiness.reasonsTitle')}
              </p>
              <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-400">
                {reasons.map((reason) => (
                  <li key={reason}>{t(`printerCost.readiness.reasons.${reason}`)}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </details>
    </div>
  );
};
