import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  CalendarClock,
  Check,
  ChevronDown,
  ChevronUp,
  CirclePause,
  CirclePlay,
  FileCode2,
  Gauge,
  History,
  Loader2,
  Plus,
  RotateCcw,
  Send,
  Spool,
  Square,
  TriangleAlert,
  X,
} from 'lucide-react';
import {
  calculatorAPI,
  orcaSlicesAPI,
  printJobsAPI,
  spoolsAPI,
  type PhysicalPrinter,
} from '../api/client';
import type {
  CalculatorHistoryEntry,
  PrintJob,
  PrintJobStatus,
} from '../types/api';
import { translateApiError } from '../utils/translateApiError';
import {
  clearIdempotencyAttempt,
  idempotencyKeyForAttempt,
} from '../utils/idempotencyAttempt';
import { ModalOverlay } from './ModalOverlay';
import { toast } from './Toast';

interface PrintJobHistoryModalProps {
  printer: PhysicalPrinter;
  onClose: () => void;
}

const TERMINAL = new Set<PrintJobStatus>(['completed', 'cancelled', 'failed']);
const PAGE_SIZE = 20;

const transitions: Record<PrintJobStatus, PrintJobStatus[]> = {
  prepared: ['sent', 'printing', 'failed', 'cancelled'],
  sent: ['printing', 'failed', 'cancelled'],
  printing: ['paused', 'completed', 'failed', 'cancelled'],
  paused: ['printing', 'completed', 'failed', 'cancelled'],
  completed: [],
  cancelled: [],
  failed: [],
};

const statusTone: Record<PrintJobStatus, string> = {
  prepared: 'border-slate-400/20 bg-slate-400/10 text-slate-200',
  sent: 'border-blue-400/20 bg-blue-400/10 text-blue-200',
  printing: 'border-cyan-400/20 bg-cyan-400/10 text-cyan-100',
  paused: 'border-amber-400/20 bg-amber-400/10 text-amber-100',
  completed: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-100',
  cancelled: 'border-slate-400/20 bg-slate-400/10 text-slate-300',
  failed: 'border-rose-400/20 bg-rose-400/10 text-rose-100',
};

const actionIcon: Record<PrintJobStatus, typeof Check> = {
  prepared: RotateCcw,
  sent: Send,
  printing: CirclePlay,
  paused: CirclePause,
  completed: Check,
  cancelled: Square,
  failed: TriangleAlert,
};

const secondsLabel = (seconds: number | null, locale: string) => {
  if (seconds == null) return null;
  const roundedMinutes = Math.max(1, Math.round(seconds / 60));
  const hours = Math.floor(roundedMinutes / 60);
  const minutes = roundedMinutes % 60;
  const values = [
    ...(hours
      ? [new Intl.NumberFormat(locale, { style: 'unit', unit: 'hour', unitDisplay: 'short' }).format(hours)]
      : []),
    ...(minutes || !hours
      ? [new Intl.NumberFormat(locale, { style: 'unit', unit: 'minute', unitDisplay: 'short' }).format(minutes)]
      : []),
  ];
  return new Intl.ListFormat(locale, { style: 'short', type: 'unit' }).format(values);
};

const calculationJobs = (entry: CalculatorHistoryEntry | undefined) =>
  entry?.parsed_jobs?.map((job) => ({
    key: job.job_key,
    label: job.parsed_gcode.file_name || job.job_key,
  })) ?? [];

export function PrintJobHistoryModal({ printer, onClose }: PrintJobHistoryModalProps) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState('');
  const [calculationId, setCalculationId] = useState('');
  const [calculatorJobKey, setCalculatorJobKey] = useState('');
  const [sliceId, setSliceId] = useState('');
  const [selectedSpools, setSelectedSpools] = useState<Set<number>>(() => new Set());
  const [expandedJobId, setExpandedJobId] = useState<number | null>(null);
  const [page, setPage] = useState(1);

  const jobsQuery = useQuery({
    queryKey: ['print-jobs', printer.id, page],
    queryFn: () =>
      printJobsAPI.list({ physical_printer_id: printer.id, page, size: PAGE_SIZE }),
  });
  const calculationsQuery = useQuery({
    queryKey: ['calculator-pro', 'history'],
    queryFn: () => calculatorAPI.listHistory({ page: 1, size: 50 }),
    enabled: creating,
    staleTime: 30_000,
  });
  const slicesQuery = useQuery({
    queryKey: ['orca-slices'],
    queryFn: () => orcaSlicesAPI.list(50),
    enabled: creating,
    staleTime: 30_000,
  });
  const spoolsQuery = useQuery({
    queryKey: ['spools'],
    queryFn: spoolsAPI.list,
    enabled: creating,
    staleTime: 30_000,
  });

  const assignedSpoolIds = useMemo(
    () =>
      new Set(
        printer.material_systems.flatMap((system) =>
          system.slots.flatMap((slot) =>
            slot.assignment?.spool_id ? [slot.assignment.spool_id] : [],
          ),
        ),
      ),
    [printer.material_systems],
  );

  useEffect(() => {
    if (creating) setSelectedSpools(new Set(assignedSpoolIds));
  }, [assignedSpoolIds, creating]);

  const selectedCalculation = calculationsQuery.data?.items.find(
    (entry) => entry.id === Number(calculationId),
  );
  const selectedCalculationJobs = calculationJobs(selectedCalculation);
  const slices = (slicesQuery.data ?? []).filter(
    (slice) => slice.physical_printer_id == null || slice.physical_printer_id === printer.id,
  );
  const spools = (spoolsQuery.data ?? []).filter(
    (spool) => spool.state !== 'archived' && spool.state !== 'empty',
  );
  const totalPages = Math.max(1, Math.ceil((jobsQuery.data?.total ?? 0) / PAGE_SIZE));
  const createAttemptStorageKey = `fh:print-job:create:${printer.id}`;

  const resetCreate = () => {
    clearIdempotencyAttempt(createAttemptStorageKey);
    setCreating(false);
    setTitle('');
    setCalculationId('');
    setCalculatorJobKey('');
    setSliceId('');
    setSelectedSpools(new Set());
  };

  const createMutation = useMutation({
    mutationFn: () => {
      const payload = {
        title: title.trim(),
        physical_printer_id: printer.id,
        calculator_history_id: calculationId ? Number(calculationId) : null,
        calculator_job_key: calculatorJobKey || null,
        orca_slice_report_id: sliceId ? Number(sliceId) : null,
        materials: Array.from(selectedSpools)
          .sort((left, right) => left - right)
          .map((spoolId) => ({ spool_id: spoolId })),
      };
      return printJobsAPI.create({
        ...payload,
        idempotency_key: idempotencyKeyForAttempt(
          createAttemptStorageKey,
          'web',
          payload,
        ),
      });
    },
    onSuccess: async () => {
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ['print-jobs', printer.id] });
      resetCreate();
      toast.success(t('printJobs.created'));
    },
    onError: (error: any) => {
      toast.error(
        translateApiError(t, error?.response?.data?.detail, t('printJobs.createError')),
      );
    },
  });

  const transitionMutation = useMutation({
    mutationFn: ({ job, status }: { job: PrintJob; status: PrintJobStatus }) => {
      const attemptStorageKey = `fh:print-job:transition:${job.id}:${status}`;
      const payload = { status };
      return printJobsAPI.transition(job.id, {
        ...payload,
        idempotency_key: idempotencyKeyForAttempt(
          attemptStorageKey,
          `web-${job.id}`,
          payload,
        ),
      });
    },
    onSuccess: async (_result, { job, status }) => {
      clearIdempotencyAttempt(`fh:print-job:transition:${job.id}:${status}`);
      await queryClient.invalidateQueries({ queryKey: ['print-jobs', printer.id] });
    },
    onError: (error: any) => {
      toast.error(
        translateApiError(t, error?.response?.data?.detail, t('printJobs.transitionError')),
      );
    },
  });

  const handleCalculation = (value: string) => {
    setCalculationId(value);
    setCalculatorJobKey('');
    if (!value || title.trim()) return;
    const entry = calculationsQuery.data?.items.find((item) => item.id === Number(value));
    if (entry) setTitle(entry.title);
  };

  const handleSlice = (value: string) => {
    setSliceId(value);
    if (!value || title.trim()) return;
    const slice = slices.find((item) => item.id === Number(value));
    if (slice) setTitle(slice.file_name.replace(/\.(?:gcode(?:\.3mf)?|3mf)$/i, ''));
  };

  return (
    <ModalOverlay
      onClose={onClose}
      contentClassName="flex min-h-full items-end justify-center sm:items-center sm:p-4"
    >
      <section className="flex max-h-[100dvh] w-full flex-col overflow-hidden rounded-t-3xl border border-white/10 bg-slate-950 shadow-2xl sm:max-h-[90dvh] sm:max-w-3xl sm:rounded-3xl">
        <header className="flex items-start gap-3 border-b border-white/10 px-4 py-4 sm:px-6">
          <div className="rounded-xl bg-cyan-400/10 p-2.5 text-cyan-200">
            <History className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-lg font-semibold text-white">
              {t('printJobs.title', { printer: printer.name })}
            </h2>
            <p className="mt-0.5 text-xs text-slate-400">{t('printJobs.subtitle')}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 transition hover:bg-white/10 hover:text-white"
            aria-label={t('common.close')}
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
          {!creating ? (
            <button
              type="button"
              onClick={() => setCreating(true)}
              className="mb-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 sm:w-auto"
            >
              <Plus className="h-4 w-4" />
              {t('printJobs.new')}
            </button>
          ) : (
            <div className="mb-6 rounded-2xl border border-cyan-400/20 bg-cyan-400/[0.055] p-4 sm:p-5">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-semibold text-white">{t('printJobs.createTitle')}</h3>
                <button
                  type="button"
                  onClick={resetCreate}
                  className="text-xs text-slate-400 transition hover:text-white"
                >
                  {t('common.cancel')}
                </button>
              </div>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <label className="sm:col-span-2">
                  <span className="mb-1.5 block text-xs font-medium text-slate-300">
                    {t('printJobs.fields.name')}
                  </span>
                  <input
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    maxLength={255}
                    placeholder={t('printJobs.fields.namePlaceholder')}
                    className="w-full rounded-xl border border-white/10 bg-slate-900 px-3 py-2.5 text-sm text-white outline-none transition focus:border-cyan-400/40"
                  />
                </label>
                <label>
                  <span className="mb-1.5 block text-xs font-medium text-slate-300">
                    {t('printJobs.fields.calculation')}
                  </span>
                  <select
                    value={calculationId}
                    onChange={(event) => handleCalculation(event.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-slate-900 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-400/40"
                  >
                    <option value="">{t('printJobs.fields.withoutCalculation')}</option>
                    {(calculationsQuery.data?.items ?? []).map((entry) => (
                      <option key={entry.id} value={entry.id}>{entry.title}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span className="mb-1.5 block text-xs font-medium text-slate-300">
                    {t('printJobs.fields.slice')}
                  </span>
                  <select
                    value={sliceId}
                    onChange={(event) => handleSlice(event.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-slate-900 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-400/40"
                  >
                    <option value="">{t('printJobs.fields.withoutSlice')}</option>
                    {slices.map((slice) => (
                      <option key={slice.id} value={slice.id}>{slice.file_name}</option>
                    ))}
                  </select>
                </label>
                {selectedCalculationJobs.length > 1 && (
                  <label className="sm:col-span-2">
                    <span className="mb-1.5 block text-xs font-medium text-slate-300">
                      {t('printJobs.fields.calculationPlate')}
                    </span>
                    <select
                      value={calculatorJobKey}
                      onChange={(event) => setCalculatorJobKey(event.target.value)}
                      className="w-full rounded-xl border border-white/10 bg-slate-900 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-400/40"
                    >
                      <option value="">{t('printJobs.fields.allPlates')}</option>
                      {selectedCalculationJobs.map((job) => (
                        <option key={job.key} value={job.key}>{job.label}</option>
                      ))}
                    </select>
                  </label>
                )}
              </div>

              <div className="mt-4">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-xs font-medium text-slate-300">
                    {t('printJobs.fields.spools')}
                  </span>
                  {assignedSpoolIds.size > 0 && (
                    <span className="text-[11px] text-cyan-200/65">
                      {t('printJobs.fields.loadedSelected')}
                    </span>
                  )}
                </div>
                {spoolsQuery.isLoading ? (
                  <Loader2 className="mt-3 h-4 w-4 animate-spin text-slate-400" />
                ) : spools.length === 0 ? (
                  <p className="mt-2 text-xs text-slate-500">{t('printJobs.fields.noSpools')}</p>
                ) : (
                  <div className="mt-2 grid max-h-44 gap-2 overflow-x-hidden overflow-y-auto pr-1 sm:grid-cols-2">
                    {spools.map((spool) => {
                      const checked = selectedSpools.has(spool.id);
                      const label = [spool.filament?.brand_name, spool.filament?.name]
                        .filter(Boolean)
                        .join(' · ') || t('printJobs.fields.unknownSpool', { id: spool.id });
                      return (
                        <label
                          key={spool.id}
                          className={`flex cursor-pointer items-center gap-2.5 rounded-xl border p-2.5 transition ${
                            checked
                              ? 'border-cyan-400/30 bg-cyan-400/10'
                              : 'border-white/10 bg-white/[0.03] hover:bg-white/[0.06]'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => {
                              setSelectedSpools((current) => {
                                const next = new Set(current);
                                if (next.has(spool.id)) next.delete(spool.id);
                                else next.add(spool.id);
                                return next;
                              });
                            }}
                            className="accent-cyan-400"
                          />
                          <span
                            className="h-3 w-3 shrink-0 rounded-full border border-white/20"
                            style={{ backgroundColor: spool.filament?.color_hex ?? '#64748b' }}
                          />
                          <span className="min-w-0 flex-1 truncate text-xs text-slate-200">{label}</span>
                          <span className="shrink-0 text-[11px] tabular-nums text-slate-500">
                            {Math.round(spool.remaining_weight_g)} g
                          </span>
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>

              <button
                type="button"
                onClick={() => createMutation.mutate()}
                disabled={!title.trim() || createMutation.isPending}
                className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400 sm:w-auto"
              >
                {createMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                {t('printJobs.create')}
              </button>
            </div>
          )}

          {jobsQuery.isLoading ? (
            <div className="flex justify-center py-14"><Loader2 className="h-6 w-6 animate-spin text-cyan-300" /></div>
          ) : jobsQuery.isError ? (
            <p className="rounded-xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-100">
              {t('printJobs.loadError')}
            </p>
          ) : (jobsQuery.data?.items.length ?? 0) === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/10 px-5 py-12 text-center">
              <History className="mx-auto h-8 w-8 text-slate-600" />
              <p className="mt-3 text-sm text-slate-300">{t('printJobs.empty')}</p>
              <p className="mt-1 text-xs text-slate-500">{t('printJobs.emptyHint')}</p>
            </div>
          ) : (
            <div className="space-y-3">
              {jobsQuery.data?.items.map((job) => {
                const expanded = expandedJobId === job.id;
                return (
                  <article key={job.id} className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
                    <div className="flex items-start gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="truncate font-medium text-white">{job.title}</h3>
                          <span className={`rounded-full border px-2 py-0.5 text-[11px] ${statusTone[job.status]}`}>
                            {t(`printJobs.status.${job.status}`)}
                          </span>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-400">
                          <span className="inline-flex items-center gap-1"><CalendarClock className="h-3.5 w-3.5" />{new Date(job.created_at).toLocaleString(i18n.language)}</span>
                          {job.file_name && <span className="inline-flex min-w-0 items-center gap-1"><FileCode2 className="h-3.5 w-3.5" /><span className="max-w-52 truncate">{job.file_name}</span></span>}
                          {(job.actual_duration_s ?? job.estimated_duration_s) != null && (
                            <span className="inline-flex items-center gap-1"><Gauge className="h-3.5 w-3.5" />{secondsLabel(job.actual_duration_s ?? job.estimated_duration_s, i18n.language)}</span>
                          )}
                          {job.materials.length > 0 && <span className="inline-flex items-center gap-1"><Spool className="h-3.5 w-3.5" />{job.materials.length}</span>}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => setExpandedJobId(expanded ? null : job.id)}
                        className="rounded-lg p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-white"
                        aria-label={expanded ? t('printJobs.collapse') : t('printJobs.expand')}
                      >
                        {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      </button>
                    </div>

                    {!TERMINAL.has(job.status) && transitions[job.status].length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2 border-t border-white/10 pt-3">
                        {transitions[job.status].map((status) => {
                          const Icon = actionIcon[status];
                          const danger = status === 'failed' || status === 'cancelled';
                          return (
                            <button
                              key={status}
                              type="button"
                              onClick={() => transitionMutation.mutate({ job, status })}
                              disabled={transitionMutation.isPending}
                              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition disabled:cursor-not-allowed disabled:opacity-30 ${
                                danger
                                  ? 'border-rose-400/15 bg-rose-400/[0.06] text-rose-200 hover:bg-rose-400/10'
                                  : 'border-white/10 bg-white/[0.045] text-slate-200 hover:bg-white/10'
                              }`}
                            >
                              <Icon className="h-3.5 w-3.5" />
                              {t(`printJobs.actions.${status}`)}
                            </button>
                          );
                        })}
                      </div>
                    )}

                    {expanded && (
                      <div className="mt-4 grid gap-4 border-t border-white/10 pt-4 sm:grid-cols-2">
                        <div>
                          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{t('printJobs.materials')}</h4>
                          {job.materials.length === 0 ? (
                            <p className="mt-2 text-xs text-slate-500">{t('printJobs.noMaterials')}</p>
                          ) : (
                            <div className="mt-2 space-y-2">
                              {job.materials.map((material) => (
                                <div key={material.id} className="flex items-center gap-2 text-xs text-slate-300">
                                  <span className="h-3 w-3 rounded-full border border-white/15" style={{ backgroundColor: material.color_hex ?? '#64748b' }} />
                                  <span className="min-w-0 flex-1 truncate">{material.spool_name}</span>
                                  {material.planned_weight_g != null && <span className="tabular-nums text-slate-500">{Math.round(material.planned_weight_g)} g</span>}
                                </div>
                              ))}
                            </div>
                          )}
                          {job.confirmed_consumption_g > 0 && (
                            <p className="mt-3 text-xs text-emerald-200/80">
                              {t('printJobs.confirmedConsumption', { value: Math.round(job.confirmed_consumption_g) })}
                            </p>
                          )}
                        </div>
                        <div>
                          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{t('printJobs.timeline')}</h4>
                          <div className="mt-2 space-y-2 border-l border-white/10 pl-3">
                            {job.events.map((event) => (
                              <div key={event.id} className="relative text-xs">
                                <span className="absolute -left-[0.95rem] top-1.5 h-1.5 w-1.5 rounded-full bg-cyan-300" />
                                <p className="text-slate-300">{t(`printJobs.status.${event.status}`)}</p>
                                <p className="text-[11px] text-slate-500">{new Date(event.occurred_at).toLocaleString(i18n.language)} · {t(`printJobs.source.${event.source}`, { defaultValue: event.source })}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </article>
                );
              })}
              {totalPages > 1 && (
                <nav
                  className="flex items-center justify-between gap-3 pt-2"
                  aria-label={t('printJobs.pagination.label')}
                >
                  <button
                    type="button"
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                    disabled={page === 1 || jobsQuery.isFetching}
                    className="rounded-lg border border-white/10 bg-white/[0.045] px-3 py-1.5 text-xs text-slate-200 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:bg-slate-900 disabled:text-slate-600"
                  >
                    {t('printJobs.pagination.previous')}
                  </button>
                  <span className="text-xs tabular-nums text-slate-500">
                    {t('printJobs.pagination.page', { page, total: totalPages })}
                  </span>
                  <button
                    type="button"
                    onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                    disabled={page === totalPages || jobsQuery.isFetching}
                    className="rounded-lg border border-white/10 bg-white/[0.045] px-3 py-1.5 text-xs text-slate-200 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:bg-slate-900 disabled:text-slate-600"
                  >
                    {t('printJobs.pagination.next')}
                  </button>
                </nav>
              )}
            </div>
          )}
        </div>
      </section>
    </ModalOverlay>
  );
}
