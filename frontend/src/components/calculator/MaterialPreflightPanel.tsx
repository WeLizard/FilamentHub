import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  PackageCheck,
  Plus,
  RefreshCw,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { UserSpool } from '../../api/client';
import { Printer3DIcon } from '../icons/Printer3DIcon';
import type {
  CalculatorPreflightLineResponse,
  CalculatorPreflightResponse,
  CalculatorPreflightStatus,
  CalculatorPrinterCompatibility,
  CalculatorPrinterCompatibilityStatus,
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

const compatibilityTone: Record<CalculatorPrinterCompatibilityStatus, string> = {
  compatible: 'border-emerald-400/20 bg-emerald-400/[0.07] text-emerald-100',
  incompatible: 'border-red-400/25 bg-red-400/[0.08] text-red-100',
  unknown: 'border-amber-400/20 bg-amber-400/[0.07] text-amber-100',
};

const compatibilityValue = (value: number, unit: string): string => {
  const formatted = Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
  return unit === '°C' ? `${formatted} °C` : `${formatted} ${unit}`;
};

const PrinterCompatibilityCard = ({ compatibility }: { compatibility: CalculatorPrinterCompatibility }) => {
  const { t } = useTranslation();
  return (
    <div className={`mt-3 rounded-2xl border p-3 ${compatibilityTone[compatibility.status]}`}>
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Printer3DIcon className="h-4 w-4 shrink-0" />
          <p className="truncate text-xs font-semibold">
            {t('profilePage.calculator.printerCompatibilityTitle', {
              name: compatibility.physical_printer_name,
            })}
          </p>
        </div>
        <span className="rounded-full border border-current/20 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.08em]">
          {t(`profilePage.calculator.printerCompatibilityStatus.${compatibility.status}`)}
        </span>
      </div>
      <p className="mt-1 text-[10px] leading-4 opacity-70">
        {t('profilePage.calculator.printerCompatibilityHint')}
      </p>
      {compatibility.checks.length > 0 ? (
        <div className="mt-2 grid gap-1.5 sm:grid-cols-2 xl:grid-cols-3">
          {compatibility.checks.map((check, index) => {
            const required = check.required_value == null
              ? '—'
              : compatibilityValue(check.required_value, check.unit);
            const available = check.available_values.length > 0
              ? check.available_values.map((value) => compatibilityValue(value, check.unit)).join(', ')
              : t('profilePage.calculator.printerCompatibilityUnknownValue');
            return (
              <div
                key={`${check.kind}-${check.job_key ?? 'manual'}-${check.line_id ?? index}`}
                className="min-w-0 rounded-xl border border-current/10 bg-black/10 px-2.5 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-[10px] font-semibold">
                    {t(`profilePage.calculator.printerCompatibilityKind.${check.kind}`)}
                  </p>
                  {check.status === 'compatible'
                    ? <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                    : <AlertTriangle className="h-3.5 w-3.5 shrink-0" />}
                </div>
                <p className="mt-0.5 text-[10px] leading-4 opacity-70">
                  {t('profilePage.calculator.printerCompatibilityValues', { required, available })}
                </p>
                {check.printer_profile_name ? (
                  <p className="mt-0.5 truncate text-[9px] opacity-55" title={check.printer_profile_name}>
                    {check.printer_profile_name}
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="mt-2 text-[10px] leading-4 opacity-70">
          {t('profilePage.calculator.printerCompatibilityNoEvidence')}
        </p>
      )}
    </div>
  );
};

const ReadinessFacts = ({ line }: { line: CalculatorPreflightLineResponse }) => {
  const { t } = useTranslation();
  const weight = (value: number) => formatWeight(
    value,
    t('profilePage.calculator.grams'),
    t('profilePage.calculator.kg'),
  );
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs">
      <span className="text-slate-400">
        {t('profilePage.calculator.preflightPlanned')}:{' '}
        <strong className="font-semibold tabular-nums text-slate-100">{weight(line.required_planned_g)}</strong>
      </span>
      {line.safety_buffer_g > 0 ? (
        <span className="tabular-nums text-slate-500">
          +{weight(line.safety_buffer_g)}
        </span>
      ) : null}
      <span className="text-slate-400">
        {t('profilePage.calculator.preflightSelectedRemaining')}:{' '}
        <strong className="font-semibold tabular-nums text-slate-100">{weight(line.selected_remaining_g)}</strong>
      </span>
    </div>
  );
};

export const MaterialPreflightPanel = ({
  result,
  safetyBufferPercent,
  isLoading,
  error,
  canRun,
  onSafetyBufferChange,
  onRefresh,
}: MaterialPreflightPanelProps) => {
  const { t } = useTranslation();
  const totalPurchaseCost = result ? formatPurchaseCost(result.purchase_cost_by_currency) : '';

  return (
    <section className="mt-4 rounded-2xl border border-white/20 bg-white/10 p-3.5 sm:p-4">
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

      {result?.printer_compatibility ? (
        <PrinterCompatibilityCard compatibility={result.printer_compatibility} />
      ) : null}

    </section>
  );
};

interface MaterialReadinessDetailsProps {
  line: MaterialPreflightUiLine;
  readiness: CalculatorPreflightLineResponse | null;
  spools: UserSpool[];
  formatSpoolLabel: (spool: UserSpool) => string;
  onSpoolIdsChange: (lineId: string, spoolIds: number[]) => void;
  /** Print with a different filament instead of the sliced one, rather than topping up. */
  onReplaceSpool: (lineId: string, spoolId: number) => void;
}

export const MaterialReadinessDetails = ({
  line,
  readiness,
  spools,
  formatSpoolLabel,
  onSpoolIdsChange,
  onReplaceSpool,
}: MaterialReadinessDetailsProps) => {
  const { t } = useTranslation();
  const weight = (value: number) => formatWeight(
    value,
    t('profilePage.calculator.grams'),
    t('profilePage.calculator.kg'),
  );
  {
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
          const replacementLeadSpool = replacementSuggestions.length > 0
            ? spools.find((item) => item.id === replacementSuggestions[0].spool_id) ?? null
            : null;
          const replacementLeadName = replacementLeadSpool ? formatSpoolLabel(replacementLeadSpool) : '';
          const uncertainAllocations = readiness?.allocations.filter(
            (allocation) => allocation.remaining_status !== 'known',
          ) ?? [];
          // A spool inside the consumption plan is removed right there; a chip below would
          // repeat both the name and the control.
          const plannedSpoolIds = new Set((readiness?.allocations ?? []).map((item) => item.spool_id));
          const selectedSpools = line.selectedSpoolIds
            .filter((spoolId) => !plannedSpoolIds.has(spoolId))
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
            <div className="mt-3 border-t border-white/10 pt-3">

              {/* Explain only what is not self-evident: an uncertain match or a weight the
                  file did not provide. When both are solid the person needs no footnote. */}
              {readiness && (readiness.evidence_source !== 'gcode' || readiness.mapping_confidence === 'low') ? (
                <p className="mt-2 text-[10px] leading-4 text-amber-200/70">
                  {[
                    readiness.evidence_source !== 'gcode'
                      ? t(`profilePage.calculator.preflightEvidence.${readiness.evidence_source}`)
                      : null,
                    readiness.mapping_confidence === 'low'
                      ? t(`profilePage.calculator.preflightConfidence.${readiness.mapping_confidence}`)
                      : null,
                  ].filter(Boolean).join(' · ')}
                </p>
              ) : null}

              <div className="mt-3 grid gap-3 lg:grid-cols-2 lg:items-start">
              <div className="min-w-0">
              {readiness ? <ReadinessFacts line={readiness} /> : null}

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
                              {suggestion.reserved_elsewhere_g > 0
                                ? ` · ${t('profilePage.calculator.preflightReservedElsewhere', { value: weight(suggestion.reserved_elsewhere_g) })}`
                                : ''}
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
                  <p className="flex items-start gap-2 text-[11px] leading-4 text-amber-100/90">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-300" />
                    <span>
                      {t('profilePage.calculator.preflightReplacementLead', { name: replacementLeadName })}
                    </span>
                  </p>
                  <p className="mt-1 pl-5 text-[10px] leading-4 text-amber-100/65">
                    {t('profilePage.calculator.preflightReplacementWarning')}
                  </p>
                  <div className="mt-2 grid gap-1.5 lg:grid-cols-2">
                    {replacementSuggestions.map((suggestion) => {
                      const spool = spools.find((item) => item.id === suggestion.spool_id);
                      if (!spool) return null;
                      return (
                        <button
                          key={`${line.lineId}-replacement-${suggestion.spool_id}`}
                          type="button"
                          onClick={() => onReplaceSpool(line.lineId, suggestion.spool_id)}
                          title={t('profilePage.calculator.preflightReplacementPick')}
                          className="min-w-0 rounded-xl border border-amber-400/10 bg-black/15 px-2.5 py-2 text-left transition hover:border-amber-300/30 hover:bg-amber-400/[0.08]"
                        >
                          <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-2 gap-y-0.5">
                            <p className="flex min-w-0 items-center gap-1.5 text-[11px] font-medium text-slate-100" title={formatSpoolLabel(spool)}>
                              {spool.filament?.color_hex ? (
                                <span
                                  className="h-2.5 w-2.5 shrink-0 rounded-full border border-white/30"
                                  style={{ backgroundColor: spool.filament.color_hex }}
                                />
                              ) : null}
                              <span className="min-w-0 truncate">{formatSpoolLabel(spool)}</span>
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
                            {suggestion.reserved_elsewhere_g > 0
                              ? ` · ${t('profilePage.calculator.preflightReservedElsewhere', { value: weight(suggestion.reserved_elsewhere_g) })}`
                              : ''}
                          </p>
                          <p className="mt-1 text-[10px] font-medium text-amber-200/80">
                            {t('profilePage.calculator.preflightReplacementPick')}
                          </p>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              </div>
              {readiness && readiness.allocations.length > 1 ? (
                <div className="min-w-0 space-y-1.5">
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
                        <div className="min-w-0 flex-1">
                          <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                            <p className="min-w-0 truncate text-[11px] font-medium text-slate-200" title={spool ? formatSpoolLabel(spool) : `#${allocation.spool_id}`}>
                              {(readiness?.allocations.length ?? 0) > 1
                                ? (spool ? formatSpoolLabel(spool) : `#${allocation.spool_id}`)
                                : t('profilePage.calculator.preflightPlanTitle')}
                            </p>
                            <span className={`shrink-0 text-[10px] tabular-nums ${remainingIsTrusted ? 'text-slate-400' : 'text-amber-200'}`}>
                              {remainingIsTrusted
                                ? t('profilePage.calculator.preflightAllocation', {
                                    consume: weight(allocation.expected_consumption_g),
                                    after: weight(allocation.expected_after_g),
                                  })
                                : t('profilePage.calculator.preflightUntrustedAllocation', {
                                    remaining: weight(allocation.remaining_before_g),
                                  })}
                            </span>
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
                            {allocation.reserved_elsewhere_g > 0
                              ? ` · ${t('profilePage.calculator.preflightReservedElsewhere', { value: weight(allocation.reserved_elsewhere_g) })}`
                              : ''}
                            {allocationCost
                              ? ` · ${t('profilePage.calculator.preflightAllocationCost', { value: allocationCost })}`
                              : ''}
                          </p>
                          {line.selectedSpoolIds.includes(allocation.spool_id) ? (
                            <div className="mt-1 flex justify-end">
                              <button
                                type="button"
                                onClick={() => onSpoolIdsChange(
                                  line.lineId,
                                  line.selectedSpoolIds.filter((id) => id !== allocation.spool_id),
                                )}
                                className="text-[10px] font-medium text-cyan-200 transition hover:text-white"
                              >
                                {t('profilePage.calculator.preflightRemoveSpool')}
                              </button>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : null}
              </div>

              <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
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
            </div>
          );
  }
};
