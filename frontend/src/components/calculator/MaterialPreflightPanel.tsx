import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  PackageCheck,
  Plus,
  RefreshCw,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { UserSpool } from '../../api/client';
import type {
  CalculatorPreflightLineResponse,
  CalculatorPreflightResponse,
  CalculatorPreflightStatus,
} from '../../types/api';
import { currencySymbol } from '../../utils/currency';
import { formatDateTime } from '../../utils/formatDate';

export interface MaterialPreflightUiLine {
  lineId: string;
  label: string;
  toolIndex: number | null;
  filamentId: number | null;
  selectedSpoolIds: number[];
}

interface MaterialPreflightPanelProps {
  lines: MaterialPreflightUiLine[];
  spools: UserSpool[];
  result: CalculatorPreflightResponse | null;
  safetyBufferPercent: number;
  isLoading: boolean;
  error: string | null;
  canRun: boolean;
  formatSpoolLabel: (spool: UserSpool) => string;
  onSafetyBufferChange: (value: number) => void;
  onSpoolIdsChange: (lineId: string, spoolIds: number[]) => void;
  onRefresh: () => void;
}

const statusTone: Record<CalculatorPreflightStatus, string> = {
  ready: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-100',
  ready_with_change: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-100',
  ready_at_risk: 'border-amber-400/25 bg-amber-400/10 text-amber-100',
  insufficient: 'border-red-400/25 bg-red-400/10 text-red-100',
  needs_clarification: 'border-amber-400/25 bg-amber-400/10 text-amber-100',
  conflict: 'border-fuchsia-400/25 bg-fuchsia-400/10 text-fuchsia-100',
};

const formatWeight = (value: number, gramsUnit: string, kilogramsUnit: string): string => {
  if (value >= 1000) return `${(value / 1000).toFixed(2)} ${kilogramsUnit}`;
  return `${Math.round(value)} ${gramsUnit}`;
};

const formatLength = (value: number): string => (
  value >= 1000 ? `${(value / 1000).toFixed(2)} m` : `${Math.round(value)} mm`
);

const formatPurchaseCost = (amounts: Record<string, number>): string => (
  Object.entries(amounts)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([currency, value]) => `${value.toFixed(2)} ${currencySymbol(currency)}`)
    .join(' + ')
);

const StatusBadge = ({ status }: { status: CalculatorPreflightStatus }) => {
  const { t } = useTranslation();
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold ${statusTone[status]}`}>
      {status === 'ready' || status === 'ready_with_change' ? (
        <CheckCircle2 className="h-3 w-3" />
      ) : (
        <AlertTriangle className="h-3 w-3" />
      )}
      {t(`profilePage.calculator.preflightStatus.${status}`)}
    </span>
  );
};

const ReadinessFacts = ({ line }: { line: CalculatorPreflightLineResponse }) => {
  const { t } = useTranslation();
  const weight = (value: number) => formatWeight(
    value,
    t('profilePage.calculator.grams'),
    t('profilePage.calculator.kg'),
  );
  const facts = [
    [t('profilePage.calculator.preflightRequired'), weight(line.required_base_g)],
    [t('profilePage.calculator.preflightBuffer'), weight(line.safety_buffer_g)],
    [t('profilePage.calculator.preflightPlanned'), weight(line.required_planned_g)],
    [t('profilePage.calculator.preflightSelectedRemaining'), weight(line.selected_remaining_g)],
  ];
  return (
    <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
      {facts.map(([label, value]) => (
        <div key={label} className="min-w-0 rounded-xl border border-white/[0.06] bg-black/15 px-3 py-2.5">
          <p className="truncate text-[10px] text-slate-500">{label}</p>
          <p className="mt-1 text-sm font-semibold tabular-nums text-slate-100">{value}</p>
        </div>
      ))}
    </div>
  );
};

export const MaterialPreflightPanel = ({
  lines,
  spools,
  result,
  safetyBufferPercent,
  isLoading,
  error,
  canRun,
  formatSpoolLabel,
  onSafetyBufferChange,
  onSpoolIdsChange,
  onRefresh,
}: MaterialPreflightPanelProps) => {
  const { t } = useTranslation();
  const weight = (value: number) => formatWeight(
    value,
    t('profilePage.calculator.grams'),
    t('profilePage.calculator.kg'),
  );
  const resultByLine = new Map(result?.lines.map((line) => [line.line_id, line]) ?? []);
  const totalPurchaseCost = result ? formatPurchaseCost(result.purchase_cost_by_currency) : '';

  return (
    <section className="mt-4 rounded-[1.15rem] border border-cyan-400/15 bg-cyan-400/[0.045] p-3.5 sm:p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-cyan-400/20 bg-cyan-400/10 text-cyan-200">
            <PackageCheck className="h-[18px] w-[18px]" />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold text-white">{t('profilePage.calculator.preflightTitle')}</h3>
              {result ? <StatusBadge status={result.status} /> : null}
            </div>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-400">
              {t('profilePage.calculator.preflightHint')}
            </p>
            {result && totalPurchaseCost ? (
              <p className="mt-1 text-xs leading-5 text-cyan-100/80">
                {t('profilePage.calculator.preflightPurchaseCost', { value: totalPurchaseCost })}
                {!result.purchase_cost_complete
                  ? ` ${t('profilePage.calculator.preflightPurchaseCostIncomplete')}`
                  : ''}
              </p>
            ) : null}
          </div>
        </div>

        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 sm:flex sm:items-end">
          <label className="min-w-0 sm:w-36">
            <span className="mb-1 block text-[10px] font-medium text-slate-400">
              {t('profilePage.calculator.preflightBufferPercent')}
            </span>
            <div className="flex items-center rounded-xl border border-white/10 bg-slate-950/60 px-3">
              <input
                type="number"
                min="0"
                max="100"
                step="1"
                value={safetyBufferPercent}
                onChange={(event) => onSafetyBufferChange(Math.min(100, Math.max(0, Number(event.target.value) || 0)))}
                className="w-full bg-transparent py-2 text-sm font-semibold tabular-nums text-white outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
              />
              <span className="text-xs text-slate-500">%</span>
            </div>
          </label>
          <button
            type="button"
            disabled={!canRun || isLoading}
            onClick={onRefresh}
            aria-label={t('profilePage.calculator.preflightRefresh')}
            title={t('profilePage.calculator.preflightRefresh')}
            className="inline-flex min-h-10 items-center justify-center gap-2 self-end rounded-xl border border-cyan-400/20 bg-cyan-400/10 px-3 text-xs font-semibold text-cyan-100 transition hover:bg-cyan-400/15 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            <span className="hidden sm:inline">{t('profilePage.calculator.preflightRefresh')}</span>
          </button>
        </div>
      </div>

      {error ? (
        <p className="mt-3 rounded-xl border border-red-400/20 bg-red-400/10 px-3 py-2 text-xs text-red-100">{error}</p>
      ) : null}

      <div className="mt-4 space-y-3">
        {lines.map((line) => {
          const readiness = resultByLine.get(line.lineId) ?? null;
          const suggestions = (readiness?.spool_suggestions ?? []).filter(
            (suggestion) => !line.selectedSpoolIds.includes(suggestion.spool_id),
          );
          const exactSuggestions = suggestions.filter((suggestion) => !suggestion.requires_reslice);
          const replacementSuggestions = suggestions.filter((suggestion) => suggestion.requires_reslice);
          const suggestedExactIds = new Set(exactSuggestions.map((suggestion) => suggestion.spool_id));
          const exactCoverageTarget = exactSuggestions[0]?.coverage_target_g ?? 0;
          const exactTrustedCoverage = exactSuggestions.reduce(
            (total, suggestion) => total + (
              suggestion.remaining_status === 'known' ? suggestion.remaining_g : 0
            ),
            0,
          );
          const showReplacementSuggestions = replacementSuggestions.length > 0
            && (exactSuggestions.length === 0 || exactTrustedCoverage < exactCoverageTarget);
          const uncertainAllocations = readiness?.allocations.filter(
            (allocation) => allocation.remaining_status !== 'known',
          ) ?? [];
          const selectedSpools = line.selectedSpoolIds
            .map((spoolId) => spools.find((spool) => spool.id === spoolId))
            .filter((spool): spool is UserSpool => spool != null);
          const candidates = spools.filter(
            (spool) => !line.selectedSpoolIds.includes(spool.id)
              && !suggestedExactIds.has(spool.id)
              && (line.filamentId == null || spool.filament_id === line.filamentId),
          );
          const needsCompatibleSpool =
            line.filamentId != null
            && selectedSpools.length === 0
            && exactSuggestions.length === 0
            && candidates.length === 0;

          return (
            <article key={line.lineId} className="rounded-2xl border border-white/[0.07] bg-black/15 p-3">
              <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-xs font-semibold text-slate-100">{line.label}</p>
                  {line.toolIndex != null ? (
                    <p className="mt-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">T{line.toolIndex}</p>
                  ) : null}
                </div>
                {readiness ? <StatusBadge status={readiness.status} /> : null}
              </div>

              {readiness ? (
                <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-slate-400">
                  <span>{t(`profilePage.calculator.preflightEvidence.${readiness.evidence_source}`)}</span>
                  <span aria-hidden="true" className="text-slate-600">·</span>
                  <span>{t(`profilePage.calculator.preflightMapping.${readiness.mapping_source}`)}</span>
                  {readiness.mapping_confidence ? (
                    <>
                      <span aria-hidden="true" className="text-slate-600">·</span>
                      <span>{t(`profilePage.calculator.preflightConfidence.${readiness.mapping_confidence}`)}</span>
                    </>
                  ) : null}
                  {readiness.required_length_mm != null && readiness.required_length_mm > 0 ? (
                    <>
                      <span aria-hidden="true" className="text-slate-600">·</span>
                      <span>{t('profilePage.calculator.preflightLength', { value: formatLength(readiness.required_length_mm) })}</span>
                    </>
                  ) : null}
                  {readiness.required_volume_cm3 != null && readiness.required_volume_cm3 > 0 ? (
                    <>
                      <span aria-hidden="true" className="text-slate-600">·</span>
                      <span>{t('profilePage.calculator.preflightVolume', { value: readiness.required_volume_cm3.toFixed(2) })}</span>
                    </>
                  ) : null}
                </div>
              ) : null}

              {readiness ? <div className="mt-3"><ReadinessFacts line={readiness} /></div> : null}

              {readiness?.status === 'ready' || readiness?.status === 'ready_with_change' ? (
                <p className="mt-2 text-xs text-emerald-200/80">
                  {t('profilePage.calculator.preflightExpectedAfter', { value: weight(readiness.expected_after_g) })}
                </p>
              ) : null}
              {readiness?.status === 'insufficient' ? (
                <p className="mt-2 text-xs text-red-200">
                  {t('profilePage.calculator.preflightShortfall', { value: weight(readiness.shortfall_base_g) })}
                </p>
              ) : null}
              {readiness?.status === 'ready_at_risk' ? (
                <p className="mt-2 text-xs text-amber-200">
                  {t('profilePage.calculator.preflightBufferShortfall', { value: weight(readiness.shortfall_buffer_g) })}
                </p>
              ) : null}
              {readiness?.status === 'needs_clarification' && uncertainAllocations.length > 0 ? (
                <div className="mt-2 flex flex-col items-start gap-1.5 rounded-xl border border-amber-400/20 bg-amber-400/[0.08] px-3 py-2 text-[11px] leading-5 text-amber-100 sm:flex-row sm:items-center sm:justify-between">
                  <p>{t('profilePage.calculator.preflightRemainingNeedsUpdate')}</p>
                  <Link
                    to="/profile?tab=spools"
                    className="shrink-0 font-semibold text-amber-200 transition hover:text-amber-100"
                  >
                    {t('profilePage.calculator.preflightReviewSpools')}
                  </Link>
                </div>
              ) : null}

              {readiness?.requires_spool_change ? (
                <p className="mt-2 text-xs text-cyan-100/80">
                  {t('profilePage.calculator.preflightChangePlan', {
                    count: readiness.allocations.filter((allocation) => allocation.sequence_index != null).length,
                  })}
                </p>
              ) : null}

              {exactSuggestions.length > 0 ? (
                <div className="mt-3 rounded-xl border border-cyan-400/20 bg-cyan-400/[0.055] p-2.5">
                  <div className="flex flex-wrap items-baseline justify-between gap-1.5">
                    <p className="text-[11px] font-semibold text-cyan-100">
                      {t('profilePage.calculator.preflightExactSuggestions')}
                    </p>
                    <p className="text-[10px] text-cyan-100/55">
                      {t('profilePage.calculator.preflightExactSuggestionsHint')}
                    </p>
                  </div>
                  <div className="mt-2 grid gap-1.5 lg:grid-cols-2">
                    {exactSuggestions.map((suggestion) => {
                      const spool = spools.find((item) => item.id === suggestion.spool_id);
                      if (!spool) return null;
                      const trusted = suggestion.remaining_status === 'known';
                      return (
                        <button
                          key={`${line.lineId}-suggestion-${suggestion.spool_id}`}
                          type="button"
                          onClick={() => onSpoolIdsChange(
                            line.lineId,
                            [...line.selectedSpoolIds, suggestion.spool_id],
                          )}
                          className="flex min-w-0 items-center gap-2 rounded-xl border border-cyan-400/15 bg-black/15 px-2.5 py-2 text-left transition hover:border-cyan-300/30 hover:bg-cyan-400/[0.08]"
                        >
                          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-cyan-400/10 text-cyan-200">
                            <Plus className="h-3.5 w-3.5" />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[11px] font-medium text-slate-100" title={formatSpoolLabel(spool)}>
                              {formatSpoolLabel(spool)}
                            </span>
                            <span className={`mt-0.5 block text-[10px] ${trusted ? 'text-slate-500' : 'text-amber-200/75'}`}>
                              {t('profilePage.calculator.preflightSuggestionCoverage', {
                                available: weight(suggestion.remaining_g),
                                target: weight(suggestion.coverage_target_g),
                              })}
                              {' · '}
                              {t(
                                suggestion.covers_target
                                  ? 'profilePage.calculator.preflightSuggestionCovers'
                                  : 'profilePage.calculator.preflightSuggestionPartial',
                              )}
                            </span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              {showReplacementSuggestions ? (
                <div className="mt-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.055] p-2.5">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-300" />
                    <div className="min-w-0">
                      <p className="text-[11px] font-semibold text-amber-100">
                        {t('profilePage.calculator.preflightReplacementSuggestions')}
                      </p>
                      <p className="mt-0.5 text-[10px] leading-4 text-amber-100/65">
                        {t('profilePage.calculator.preflightReplacementWarning')}
                      </p>
                    </div>
                  </div>
                  <div className="mt-2 grid gap-1.5 lg:grid-cols-2">
                    {replacementSuggestions.map((suggestion) => {
                      const spool = spools.find((item) => item.id === suggestion.spool_id);
                      if (!spool) return null;
                      return (
                        <div
                          key={`${line.lineId}-replacement-${suggestion.spool_id}`}
                          className="min-w-0 rounded-xl border border-amber-400/10 bg-black/15 px-2.5 py-2"
                        >
                          <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
                            <p className="min-w-0 truncate text-[11px] font-medium text-slate-100" title={formatSpoolLabel(spool)}>
                              {formatSpoolLabel(spool)}
                            </p>
                            <span className="shrink-0 text-[9px] font-semibold uppercase tracking-[0.08em] text-amber-300/75">
                              {t(`profilePage.calculator.preflightSuggestionRelation.${suggestion.relation}`)}
                            </span>
                          </div>
                          <p className="mt-0.5 text-[10px] text-slate-500">
                            {t('profilePage.calculator.preflightSuggestionCoverage', {
                              available: weight(suggestion.remaining_g),
                              target: weight(suggestion.coverage_target_g),
                            })}
                            {' · '}
                            {t(`profilePage.calculator.preflightRemainingStatus.${suggestion.remaining_status}`)}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              {readiness && readiness.allocations.length > 0 ? (
                <div className="mt-3 space-y-1.5">
                  {readiness.allocations.map((allocation) => {
                    const spool = spools.find((item) => item.id === allocation.spool_id);
                    const remainingIsTrusted = allocation.remaining_status === 'known';
                    const allocationCost = allocation.expected_purchase_cost != null && allocation.purchase_currency
                      ? `${allocation.expected_purchase_cost.toFixed(2)} ${currencySymbol(allocation.purchase_currency)}`
                      : null;
                    return (
                      <div
                        key={`${line.lineId}-plan-${allocation.spool_id}`}
                        className={`grid min-w-0 grid-cols-[auto_minmax(0,1fr)] gap-x-2 rounded-xl border px-2.5 py-2 ${
                          remainingIsTrusted
                            ? 'border-white/[0.06] bg-white/[0.025]'
                            : 'border-amber-400/20 bg-amber-400/[0.06]'
                        }`}
                      >
                        <span className={`mt-0.5 flex h-5 min-w-5 items-center justify-center rounded-md px-1.5 text-[10px] font-semibold ${
                          remainingIsTrusted
                            ? 'bg-cyan-400/10 text-cyan-200'
                            : 'bg-amber-400/10 text-amber-200'
                        }`}>
                          {remainingIsTrusted ? (allocation.sequence_index ?? '—') : <AlertTriangle className="h-3 w-3" />}
                        </span>
                        <div className="min-w-0">
                          <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                            <p className="min-w-0 truncate text-[11px] font-medium text-slate-200" title={spool ? formatSpoolLabel(spool) : `#${allocation.spool_id}`}>
                              {spool ? formatSpoolLabel(spool) : `#${allocation.spool_id}`}
                            </p>
                            <p className={`shrink-0 text-[10px] tabular-nums ${remainingIsTrusted ? 'text-slate-400' : 'text-amber-200'}`}>
                              {remainingIsTrusted
                                ? t('profilePage.calculator.preflightAllocation', {
                                    consume: weight(allocation.expected_consumption_g),
                                    after: weight(allocation.expected_after_g),
                                  })
                                : t('profilePage.calculator.preflightUntrustedAllocation', {
                                    remaining: weight(allocation.remaining_before_g),
                                  })}
                            </p>
                          </div>
                          <p className={`mt-0.5 text-[10px] leading-4 ${remainingIsTrusted ? 'text-slate-500' : 'text-amber-100/65'}`}>
                            {t(`profilePage.calculator.preflightRemainingEvidence.${allocation.remaining_evidence}`)}
                            {' · '}
                            {t(`profilePage.calculator.preflightRemainingStatus.${allocation.remaining_status}`)}
                            {' · '}
                            {t(`profilePage.calculator.preflightRemainingConfidence.${allocation.remaining_confidence}`)}
                            {' · '}
                            {t('profilePage.calculator.preflightInventoryUpdated', {
                              value: formatDateTime(allocation.remaining_updated_at),
                            })}
                            {allocationCost
                              ? ` · ${t('profilePage.calculator.preflightAllocationCost', { value: allocationCost })}`
                              : ''}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : null}

              <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
                {selectedSpools.map((spool) => {
                  return (
                    <span
                      key={`${line.lineId}-${spool.id}`}
                      className="inline-flex min-w-0 items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/[0.045] px-2.5 py-2 text-[11px] text-slate-200 sm:max-w-sm"
                    >
                      <span className="min-w-0 truncate" title={formatSpoolLabel(spool)}>
                        {formatSpoolLabel(spool)}
                      </span>
                      <button
                        type="button"
                        onClick={() => onSpoolIdsChange(line.lineId, line.selectedSpoolIds.filter((id) => id !== spool.id))}
                        className="shrink-0 rounded-md p-0.5 text-slate-500 transition hover:bg-white/10 hover:text-white"
                        aria-label={t('profilePage.calculator.preflightRemoveSpool')}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </span>
                  );
                })}

                {candidates.length > 0 ? (
                  <label className="relative min-w-0 sm:max-w-sm sm:flex-1">
                    <Plus className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-cyan-300" />
                    <select
                      value=""
                      aria-label={t('profilePage.calculator.preflightAddSpool')}
                      onChange={(event) => {
                        const spoolId = Number(event.target.value);
                        if (spoolId > 0) onSpoolIdsChange(line.lineId, [...line.selectedSpoolIds, spoolId]);
                      }}
                      className="w-full appearance-none rounded-xl border border-dashed border-cyan-400/25 bg-cyan-400/[0.04] py-2 pl-9 pr-3 text-xs text-cyan-100 outline-none transition hover:bg-cyan-400/[0.08] focus:ring-2 focus:ring-cyan-400/40"
                    >
                      <option value="">{t('profilePage.calculator.preflightAddSpool')}</option>
                      {candidates.map((spool) => (
                        <option key={`${line.lineId}-candidate-${spool.id}`} value={spool.id}>
                          {formatSpoolLabel(spool)}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
              </div>

              {line.selectedSpoolIds.length === 0 ? (
                <div className="mt-2 flex flex-col items-start gap-1.5 text-[11px] leading-5 text-slate-500 sm:flex-row sm:items-center sm:justify-between">
                  <p>
                    {t(
                      needsCompatibleSpool
                        ? 'profilePage.calculator.preflightNoCompatibleSpool'
                        : 'profilePage.calculator.preflightNoPhysicalSpool',
                    )}
                  </p>
                  {needsCompatibleSpool ? (
                    <Link
                      to={`/profile?tab=spools&add_spool=1&filament_id=${line.filamentId}`}
                      className="shrink-0 font-semibold text-cyan-300 transition hover:text-cyan-200"
                    >
                      {t('profilePage.calculator.preflightAddOwnedSpool')}
                    </Link>
                  ) : null}
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
};
