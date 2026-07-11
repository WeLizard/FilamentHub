/** CRM-lite workspace for customers, commercial proposals, and accepted orders. */

import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Archive,
  ArrowRight,
  BriefcaseBusiness,
  Check,
  ChevronRight,
  CloudDownload,
  Copy,
  FileCheck2,
  FileText,
  Loader2,
  PackageCheck,
  Plus,
  Search,
  Send,
  Sparkles,
  UserRound,
  UsersRound,
  X,
} from 'lucide-react';

import { calculatorAPI, crmAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { translateApiError } from '../utils/translateApiError';
import type {
  CrmCustomer,
  CrmCustomerCreate,
  CrmOrder,
  CrmOrderStatus,
  CrmQuote,
  CrmQuoteDetail,
  CrmQuoteStatus,
} from '../types/api';

type WorkspaceTab = 'quotes' | 'orders' | 'customers';
type Feedback = { kind: 'success' | 'error'; text: string } | null;

const surfaceClass =
  'rounded-[1.75rem] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.9),rgba(15,23,42,0.76))] shadow-[0_30px_90px_-55px_rgba(2,6,23,0.95)] backdrop-blur-xl';
const inputClass =
  'w-full rounded-xl border border-white/10 bg-slate-950/60 px-3.5 py-2.5 text-sm text-white placeholder:text-slate-500 outline-none transition focus:border-cyan-400/45 focus:ring-2 focus:ring-cyan-400/15';

const QUOTE_TRANSITIONS: Record<CrmQuoteStatus, CrmQuoteStatus[]> = {
  draft: ['sent', 'accepted', 'rejected'],
  sent: ['draft', 'accepted', 'rejected', 'expired'],
  accepted: [],
  rejected: ['draft'],
  expired: ['draft'],
};

const ORDER_TRANSITIONS: Record<CrmOrderStatus, CrmOrderStatus[]> = {
  new: ['planned', 'in_production', 'cancelled'],
  planned: ['new', 'in_production', 'cancelled'],
  in_production: ['planned', 'ready', 'cancelled'],
  ready: ['in_production', 'completed', 'cancelled'],
  completed: [],
  cancelled: ['new'],
};

const statusTone: Record<CrmQuoteStatus | CrmOrderStatus, string> = {
  draft: 'border-slate-400/20 bg-slate-400/10 text-slate-200',
  sent: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-100',
  accepted: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-100',
  rejected: 'border-rose-400/25 bg-rose-400/10 text-rose-100',
  expired: 'border-amber-400/25 bg-amber-400/10 text-amber-100',
  new: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-100',
  planned: 'border-blue-400/25 bg-blue-400/10 text-blue-100',
  in_production: 'border-violet-400/25 bg-violet-400/10 text-violet-100',
  ready: 'border-amber-400/25 bg-amber-400/10 text-amber-100',
  completed: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-100',
  cancelled: 'border-rose-400/25 bg-rose-400/10 text-rose-100',
};

const formatDate = (value: string | null | undefined): string => (
  value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value))
    : '—'
);

const makeCurrencyFormatter = (currency: string) => {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 2 });
  } catch {
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
  }
};

const formatCurrencyBreakdown = (amounts: Record<string, number> | undefined): string => {
  if (!amounts) return '—';
  const entries = Object.entries(amounts).filter(([, value]) => value !== 0);
  if (entries.length === 0) return '0';
  return entries.map(([currency, value]) => makeCurrencyFormatter(currency).format(value)).join(' · ');
};

export const CrmWorkspacePage: React.FC = () => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('quotes');
  const [search, setSearch] = useState('');
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [customerDialog, setCustomerDialog] = useState<CrmCustomer | 'new' | null>(null);
  const [selectedQuoteId, setSelectedQuoteId] = useState<number | null>(null);
  const hasAccess = user?.has_calculator_access ?? false;

  const summaryQuery = useQuery({
    queryKey: ['crm', 'summary'],
    queryFn: crmAPI.getSummary,
    enabled: hasAccess,
  });
  const customersQuery = useQuery({
    queryKey: ['crm', 'customers', search],
    queryFn: () => crmAPI.listCustomers({ search: search || undefined, size: 100 }),
    enabled: hasAccess,
  });
  const quotesQuery = useQuery({
    queryKey: ['crm', 'quotes', search],
    queryFn: () => crmAPI.listQuotes({ search: search || undefined, size: 100 }),
    enabled: hasAccess,
  });
  const ordersQuery = useQuery({
    queryKey: ['crm', 'orders', search],
    queryFn: () => crmAPI.listOrders({ search: search || undefined, size: 100 }),
    enabled: hasAccess,
  });
  const quoteDetailQuery = useQuery({
    queryKey: ['crm', 'quote', selectedQuoteId],
    queryFn: () => crmAPI.getQuote(selectedQuoteId!),
    enabled: hasAccess && selectedQuoteId !== null,
  });

  const refreshWorkspace = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['crm', 'summary'] }),
      queryClient.invalidateQueries({ queryKey: ['crm', 'customers'] }),
      queryClient.invalidateQueries({ queryKey: ['crm', 'quotes'] }),
      queryClient.invalidateQueries({ queryKey: ['crm', 'orders'] }),
      queryClient.invalidateQueries({ queryKey: ['crm', 'quote'] }),
    ]);
  };

  const quoteStatusMutation = useMutation({
    mutationFn: ({ quoteId, status }: { quoteId: number; status: CrmQuoteStatus }) => (
      crmAPI.updateQuoteStatus(quoteId, status)
    ),
    onSuccess: async () => {
      setFeedback({ kind: 'success', text: t('crmWorkspace.feedback.quoteStatus') });
      await refreshWorkspace();
    },
    onError: (error) => setFeedback({
      kind: 'error',
      text: translateApiError(t, error, t('crmWorkspace.feedback.error')),
    }),
  });

  const quoteCustomerMutation = useMutation({
    mutationFn: ({ quoteId, customerId }: { quoteId: number; customerId: number | null }) => (
      crmAPI.updateQuote(quoteId, { customer_id: customerId })
    ),
    onSuccess: async () => {
      setFeedback({ kind: 'success', text: t('crmWorkspace.feedback.quoteCustomer') });
      await refreshWorkspace();
    },
    onError: (error) => setFeedback({
      kind: 'error',
      text: translateApiError(t, error, t('crmWorkspace.feedback.error')),
    }),
  });

  const orderMutation = useMutation({
    mutationFn: ({ orderId, status }: { orderId: number; status: CrmOrderStatus }) => (
      crmAPI.updateOrder(orderId, { status })
    ),
    onSuccess: async () => {
      setFeedback({ kind: 'success', text: t('crmWorkspace.feedback.orderStatus') });
      await refreshWorkspace();
    },
    onError: (error) => setFeedback({
      kind: 'error',
      text: translateApiError(t, error, t('crmWorkspace.feedback.error')),
    }),
  });

  const customerMutation = useMutation({
    mutationFn: async ({ id, payload }: { id?: number; payload: CrmCustomerCreate }) => (
      id ? crmAPI.updateCustomer(id, payload) : crmAPI.createCustomer(payload)
    ),
    onSuccess: async () => {
      setCustomerDialog(null);
      setFeedback({ kind: 'success', text: t('crmWorkspace.feedback.customerSaved') });
      await refreshWorkspace();
    },
    onError: (error) => setFeedback({
      kind: 'error',
      text: translateApiError(t, error, t('crmWorkspace.feedback.error')),
    }),
  });

  const archiveCustomerMutation = useMutation({
    mutationFn: (customerId: number) => crmAPI.updateCustomer(customerId, { archived: true }),
    onSuccess: refreshWorkspace,
    onError: (error) => setFeedback({
      kind: 'error',
      text: translateApiError(t, error, t('crmWorkspace.feedback.error')),
    }),
  });

  const shareMutation = useMutation({
    mutationFn: crmAPI.shareQuote,
    onSuccess: async (shared) => {
      await navigator.clipboard.writeText(shared.share_url);
      setFeedback({ kind: 'success', text: t('crmWorkspace.feedback.linkCopied') });
      await refreshWorkspace();
    },
    onError: (error) => setFeedback({
      kind: 'error',
      text: translateApiError(t, error, t('crmWorkspace.feedback.error')),
    }),
  });

  const downloadPdf = async (quote: CrmQuote | CrmQuoteDetail) => {
    if (!quote.current_version.html_content) {
      setFeedback({ kind: 'error', text: t('crmWorkspace.feedback.noDocument') });
      return;
    }
    try {
      await calculatorAPI.downloadQuotePdf({
        title: quote.number,
        html_content: quote.current_version.html_content,
      });
    } catch (error) {
      setFeedback({ kind: 'error', text: translateApiError(t, error, t('crmWorkspace.feedback.error')) });
    }
  };

  if (!hasAccess) {
    return (
      <div className="mx-auto max-w-2xl py-10">
        <section className={`${surfaceClass} p-8 text-center md:p-12`}>
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10">
            <BriefcaseBusiness className="h-8 w-8 text-cyan-200" />
          </div>
          <h1 className="mt-5 text-2xl font-bold text-white">{t('crmWorkspace.locked.title')}</h1>
          <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-300">{t('crmWorkspace.locked.description')}</p>
          <Link
            to="/calculator"
            className="mt-6 inline-flex items-center gap-2 rounded-xl bg-cyan-500 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300"
          >
            {t('crmWorkspace.locked.action')}
            <ArrowRight className="h-4 w-4" />
          </Link>
        </section>
      </div>
    );
  }

  const summary = summaryQuery.data;
  const isCurrentLoading = activeTab === 'quotes'
    ? quotesQuery.isPending
    : activeTab === 'orders'
      ? ordersQuery.isPending
      : customersQuery.isPending;

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-[2rem] border border-white/10 bg-slate-950/70 shadow-2xl shadow-slate-950/35">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_10%_0%,rgba(34,211,238,0.2),transparent_32%),radial-gradient(circle_at_90%_20%,rgba(245,158,11,0.14),transparent_28%)]" />
        <div className="relative p-6 md:p-8">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-amber-300/20 bg-amber-300/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-amber-100">
                <Sparkles className="h-3.5 w-3.5" />
                {t('crmWorkspace.badge')}
              </div>
              <h1 className="mt-4 text-3xl font-bold tracking-tight text-white md:text-4xl">{t('crmWorkspace.title')}</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300 md:text-base">{t('crmWorkspace.subtitle')}</p>
            </div>
            <Link
              to="/calculator"
              className="inline-flex w-fit items-center gap-2 rounded-xl border border-cyan-400/25 bg-cyan-400/10 px-4 py-3 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-400/20"
            >
              <Plus className="h-4 w-4" />
              {t('crmWorkspace.newCalculation')}
            </Link>
          </div>

          <div className="mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard icon={<Send />} label={t('crmWorkspace.metrics.awaiting')} value={formatCurrencyBreakdown(summary?.amount_awaiting_decision)} />
            <MetricCard icon={<FileCheck2 />} label={t('crmWorkspace.metrics.accepted')} value={summary ? String(summary.quotes_accepted) : '—'} />
            <MetricCard icon={<PackageCheck />} label={t('crmWorkspace.metrics.activeOrders')} value={summary ? String(summary.orders_active) : '—'} />
            <MetricCard icon={<UsersRound />} label={t('crmWorkspace.metrics.customers')} value={summary ? String(summary.customers_total) : '—'} />
          </div>
        </div>
      </section>

      <section className={`${surfaceClass} p-4 md:p-5`}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-2">
            <WorkspaceTabButton active={activeTab === 'quotes'} icon={<FileText />} label={t('crmWorkspace.tabs.quotes')} count={quotesQuery.data?.total} onClick={() => setActiveTab('quotes')} />
            <WorkspaceTabButton active={activeTab === 'orders'} icon={<BriefcaseBusiness />} label={t('crmWorkspace.tabs.orders')} count={ordersQuery.data?.total} onClick={() => setActiveTab('orders')} />
            <WorkspaceTabButton active={activeTab === 'customers'} icon={<UsersRound />} label={t('crmWorkspace.tabs.customers')} count={customersQuery.data?.total} onClick={() => setActiveTab('customers')} />
          </div>
          <div className="flex w-full gap-2 lg:w-auto">
            <label className="relative min-w-0 flex-1 lg:w-72">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
              <input value={search} onChange={(event) => setSearch(event.target.value)} className={`${inputClass} pl-9`} placeholder={t('crmWorkspace.search')} />
            </label>
            {activeTab === 'customers' && (
              <button type="button" onClick={() => setCustomerDialog('new')} className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300">
                <Plus className="h-4 w-4" />
                <span className="hidden sm:inline">{t('crmWorkspace.customers.add')}</span>
              </button>
            )}
          </div>
        </div>

        {feedback && (
          <div className={`mt-4 flex items-start justify-between gap-3 rounded-xl border px-4 py-3 text-sm ${feedback.kind === 'success' ? 'border-emerald-400/20 bg-emerald-400/10 text-emerald-100' : 'border-rose-400/20 bg-rose-400/10 text-rose-100'}`}>
            <span>{feedback.text}</span>
            <button type="button" onClick={() => setFeedback(null)}><X className="h-4 w-4" /></button>
          </div>
        )}

        <div className="mt-5">
          {isCurrentLoading ? (
            <div className="flex min-h-56 items-center justify-center"><Loader2 className="h-7 w-7 animate-spin text-cyan-300" /></div>
          ) : activeTab === 'quotes' ? (
            <QuotesList
              quotes={quotesQuery.data?.items ?? []}
              onOpen={setSelectedQuoteId}
              onStatus={(quoteId, status) => quoteStatusMutation.mutate({ quoteId, status })}
              onShare={(quoteId) => shareMutation.mutate(quoteId)}
              onPdf={(quote) => void downloadPdf(quote)}
              busy={quoteStatusMutation.isPending || shareMutation.isPending}
            />
          ) : activeTab === 'orders' ? (
            <OrdersList
              orders={ordersQuery.data?.items ?? []}
              onStatus={(orderId, status) => orderMutation.mutate({ orderId, status })}
              busy={orderMutation.isPending}
            />
          ) : (
            <CustomersList
              customers={customersQuery.data?.items ?? []}
              onEdit={setCustomerDialog}
              onArchive={(id) => archiveCustomerMutation.mutate(id)}
              busy={archiveCustomerMutation.isPending}
            />
          )}
        </div>
      </section>

      <CustomerDialog
        customer={customerDialog}
        isSaving={customerMutation.isPending}
        onClose={() => setCustomerDialog(null)}
        onSave={(payload) => customerMutation.mutate({
          id: customerDialog && customerDialog !== 'new' ? customerDialog.id : undefined,
          payload,
        })}
      />
      <QuoteDetailDrawer
        quote={quoteDetailQuery.data ?? null}
        customers={customersQuery.data?.items ?? []}
        isLoading={quoteDetailQuery.isPending && selectedQuoteId !== null}
        onClose={() => setSelectedQuoteId(null)}
        onStatus={(status) => selectedQuoteId && quoteStatusMutation.mutate({ quoteId: selectedQuoteId, status })}
        onCustomer={(customerId) => selectedQuoteId && quoteCustomerMutation.mutate({ quoteId: selectedQuoteId, customerId })}
        onShare={() => selectedQuoteId && shareMutation.mutate(selectedQuoteId)}
        onPdf={(quote) => void downloadPdf(quote)}
        busy={quoteStatusMutation.isPending || quoteCustomerMutation.isPending || shareMutation.isPending}
      />
    </div>
  );
};

const MetricCard: React.FC<{ icon: ReactNode; label: string; value: string }> = ({ icon, label, value }) => (
  <div className="rounded-2xl border border-white/10 bg-black/20 px-4 py-4">
    <div className="flex items-center gap-2 text-slate-400 [&>svg]:h-4 [&>svg]:w-4 [&>svg]:text-cyan-300">
      {icon}<span className="text-xs font-medium uppercase tracking-[0.13em]">{label}</span>
    </div>
    <p className="mt-3 text-2xl font-semibold tracking-tight text-white">{value}</p>
  </div>
);

const WorkspaceTabButton: React.FC<{ active: boolean; icon: ReactNode; label: string; count?: number; onClick: () => void }> = ({ active, icon, label, count, onClick }) => (
  <button type="button" onClick={onClick} className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-2.5 text-sm font-medium transition ${active ? 'border-cyan-400/30 bg-cyan-400/15 text-cyan-50' : 'border-white/10 bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white'} [&>svg]:h-4 [&>svg]:w-4`}>
    {icon}<span>{label}</span>{count !== undefined && <span className="rounded-full bg-black/20 px-2 py-0.5 text-xs">{count}</span>}
  </button>
);

const StatusBadge: React.FC<{ status: CrmQuoteStatus | CrmOrderStatus; kind: 'quote' | 'order' }> = ({ status, kind }) => {
  const { t } = useTranslation();
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${statusTone[status]}`}>{t(`crmWorkspace.status.${kind}.${status}`)}</span>;
};

const StatusSelect = <T extends string>({ value, options, label, onChange, disabled }: { value: T; options: T[]; label: (status: T) => string; onChange: (status: T) => void; disabled: boolean }) => (
  <select value="" disabled={disabled || options.length === 0} onChange={(event) => { if (event.target.value) onChange(event.target.value as T); }} className="rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none disabled:cursor-not-allowed disabled:opacity-45">
    <option value="">{options.length > 0 ? label(value) : '—'}</option>
    {options.map((status) => <option key={status} value={status}>{label(status)}</option>)}
  </select>
);

const QuotesList: React.FC<{ quotes: CrmQuote[]; onOpen: (id: number) => void; onStatus: (id: number, status: CrmQuoteStatus) => void; onShare: (id: number) => void; onPdf: (quote: CrmQuote) => void; busy: boolean }> = ({ quotes, onOpen, onStatus, onShare, onPdf, busy }) => {
  const { t } = useTranslation();
  if (quotes.length === 0) return <EmptyState icon={<FileText />} title={t('crmWorkspace.quotes.emptyTitle')} text={t('crmWorkspace.quotes.emptyText')} action={<Link to="/calculator" className="text-sm font-semibold text-cyan-200 hover:text-cyan-100">{t('crmWorkspace.newCalculation')}</Link>} />;
  return <div className="space-y-3">{quotes.map((quote) => {
    const formatter = makeCurrencyFormatter(quote.currency);
    return (
      <article key={quote.id} className="group rounded-2xl border border-white/10 bg-white/[0.035] p-4 transition hover:border-white/20 hover:bg-white/[0.055] md:p-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center">
          <button type="button" onClick={() => onOpen(quote.id)} className="min-w-0 flex-1 text-left">
            <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs text-cyan-300">{quote.number}</span><StatusBadge status={quote.status} kind="quote" /><span className="text-xs text-slate-500">v{quote.current_version.version_number}</span></div>
            <h2 className="mt-2 truncate text-lg font-semibold text-white group-hover:text-cyan-50">{quote.title}</h2>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400"><span>{quote.customer?.name ?? t('crmWorkspace.quotes.noCustomer')}</span><span>{t('crmWorkspace.quotes.validUntil')}: {formatDate(quote.valid_until)}</span><span>{quote.current_version.lines.length} {t('crmWorkspace.quotes.positions')}</span></div>
          </button>
          <div className="flex flex-wrap items-center gap-2 xl:justify-end">
            <span className="mr-2 text-lg font-semibold text-white">{formatter.format(quote.current_version.grand_total)}</span>
            <StatusSelect value={quote.status} options={QUOTE_TRANSITIONS[quote.status]} label={(status) => t(`crmWorkspace.status.quote.${status}`)} onChange={(status) => onStatus(quote.id, status)} disabled={busy} />
            <button type="button" onClick={() => onPdf(quote)} disabled={!quote.current_version.html_content} className="rounded-xl border border-white/10 bg-white/5 p-2.5 text-slate-300 transition hover:bg-white/10 hover:text-white disabled:opacity-35" title={t('crmWorkspace.actions.pdf')}><CloudDownload className="h-4 w-4" /></button>
            <button type="button" onClick={() => onShare(quote.id)} disabled={busy || !quote.current_version.html_content} className="rounded-xl border border-white/10 bg-white/5 p-2.5 text-slate-300 transition hover:bg-white/10 hover:text-white disabled:opacity-35" title={t('crmWorkspace.actions.share')}><Copy className="h-4 w-4" /></button>
            <button type="button" onClick={() => onOpen(quote.id)} className="rounded-xl border border-white/10 bg-white/5 p-2.5 text-slate-300 transition hover:bg-white/10 hover:text-white"><ChevronRight className="h-4 w-4" /></button>
          </div>
        </div>
      </article>
    );
  })}</div>;
};

const OrdersList: React.FC<{ orders: CrmOrder[]; onStatus: (id: number, status: CrmOrderStatus) => void; busy: boolean }> = ({ orders, onStatus, busy }) => {
  const { t } = useTranslation();
  if (orders.length === 0) return <EmptyState icon={<BriefcaseBusiness />} title={t('crmWorkspace.orders.emptyTitle')} text={t('crmWorkspace.orders.emptyText')} />;
  return <div className="grid gap-3 lg:grid-cols-2">{orders.map((order) => (
    <article key={order.id} className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
      <div className="flex items-start justify-between gap-4"><div><p className="font-mono text-xs text-cyan-300">{order.number}</p><h2 className="mt-2 text-lg font-semibold text-white">{order.title}</h2><p className="mt-1 text-sm text-slate-400">{order.customer?.name ?? t('crmWorkspace.quotes.noCustomer')}</p></div><StatusBadge status={order.status} kind="order" /></div>
      <div className="mt-5 grid grid-cols-2 gap-3 rounded-xl border border-white/5 bg-black/15 p-3 text-sm"><div><p className="text-xs text-slate-500">{t('crmWorkspace.orders.amount')}</p><p className="mt-1 font-semibold text-white">{makeCurrencyFormatter(order.currency).format(order.total)}</p></div><div><p className="text-xs text-slate-500">{t('crmWorkspace.orders.dueDate')}</p><p className="mt-1 font-medium text-slate-200">{formatDate(order.due_date)}</p></div></div>
      <div className="mt-4 flex items-center justify-between gap-3"><span className="text-xs text-slate-500">{t('crmWorkspace.orders.fromQuote')}</span><StatusSelect value={order.status} options={ORDER_TRANSITIONS[order.status]} label={(status) => t(`crmWorkspace.status.order.${status}`)} onChange={(status) => onStatus(order.id, status)} disabled={busy} /></div>
    </article>
  ))}</div>;
};

const CustomersList: React.FC<{ customers: CrmCustomer[]; onEdit: (customer: CrmCustomer) => void; onArchive: (id: number) => void; busy: boolean }> = ({ customers, onEdit, onArchive, busy }) => {
  const { t } = useTranslation();
  if (customers.length === 0) return <EmptyState icon={<UsersRound />} title={t('crmWorkspace.customers.emptyTitle')} text={t('crmWorkspace.customers.emptyText')} />;
  return <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{customers.map((customer) => (
    <article key={customer.id} className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
      <div className="flex items-start justify-between gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl border border-cyan-400/15 bg-cyan-400/10"><UserRound className="h-5 w-5 text-cyan-200" /></div><button type="button" onClick={() => onArchive(customer.id)} disabled={busy} className="rounded-lg p-2 text-slate-500 transition hover:bg-white/5 hover:text-amber-200" title={t('crmWorkspace.customers.archive')}><Archive className="h-4 w-4" /></button></div>
      <button type="button" onClick={() => onEdit(customer)} className="mt-4 block w-full text-left"><h2 className="truncate text-base font-semibold text-white hover:text-cyan-100">{customer.name}</h2><p className="mt-1 truncate text-sm text-slate-400">{customer.contact_name || customer.email || customer.phone || t('crmWorkspace.customers.noContacts')}</p></button>
      <div className="mt-4 space-y-1 text-xs text-slate-500">{customer.phone && <p>{customer.phone}</p>}{customer.email && <p className="truncate">{customer.email}</p>}{customer.inn && <p>{t('crmWorkspace.customers.inn')}: {customer.inn}</p>}</div>
    </article>
  ))}</div>;
};

const EmptyState: React.FC<{ icon: ReactNode; title: string; text: string; action?: ReactNode }> = ({ icon, title, text, action }) => (
  <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-black/10 px-6 text-center"><div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-slate-400 [&>svg]:h-6 [&>svg]:w-6">{icon}</div><h2 className="mt-4 text-lg font-semibold text-white">{title}</h2><p className="mt-2 max-w-md text-sm leading-6 text-slate-400">{text}</p>{action && <div className="mt-4">{action}</div>}</div>
);

const CustomerDialog: React.FC<{ customer: CrmCustomer | 'new' | null; isSaving: boolean; onClose: () => void; onSave: (payload: CrmCustomerCreate) => void }> = ({ customer, isSaving, onClose, onSave }) => {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<CrmCustomerCreate>({ name: '' });
  useEffect(() => {
    setDraft(customer && customer !== 'new'
      ? { name: customer.name, contact_name: customer.contact_name, email: customer.email, phone: customer.phone, inn: customer.inn, address: customer.address, note: customer.note }
      : { name: '' });
  }, [customer]);
  if (!customer) return null;
  return <div className="fixed inset-0 z-[70] flex items-center justify-center overflow-y-auto bg-slate-950/75 p-4 backdrop-blur-md" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className={`${surfaceClass} w-full max-w-2xl p-6 md:p-7`}><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-300">{t('crmWorkspace.customers.cardLabel')}</p><h2 className="mt-2 text-2xl font-semibold text-white">{customer === 'new' ? t('crmWorkspace.customers.createTitle') : t('crmWorkspace.customers.editTitle')}</h2></div><button type="button" onClick={onClose} className="rounded-xl border border-white/10 bg-white/5 p-2.5 text-slate-300 hover:bg-white/10"><X className="h-5 w-5" /></button></div><div className="mt-6 grid gap-4 md:grid-cols-2"><DialogField label={t('crmWorkspace.customers.name')}><input className={inputClass} value={draft.name} onChange={(event) => setDraft((prev) => ({ ...prev, name: event.target.value }))} autoFocus /></DialogField><DialogField label={t('crmWorkspace.customers.contactName')}><input className={inputClass} value={draft.contact_name ?? ''} onChange={(event) => setDraft((prev) => ({ ...prev, contact_name: event.target.value }))} /></DialogField><DialogField label={t('crmWorkspace.customers.phone')}><input className={inputClass} value={draft.phone ?? ''} onChange={(event) => setDraft((prev) => ({ ...prev, phone: event.target.value }))} /></DialogField><DialogField label={t('crmWorkspace.customers.email')}><input type="email" className={inputClass} value={draft.email ?? ''} onChange={(event) => setDraft((prev) => ({ ...prev, email: event.target.value }))} /></DialogField><DialogField label={t('crmWorkspace.customers.inn')}><input className={inputClass} value={draft.inn ?? ''} onChange={(event) => setDraft((prev) => ({ ...prev, inn: event.target.value }))} /></DialogField><DialogField label={t('crmWorkspace.customers.address')}><input className={inputClass} value={draft.address ?? ''} onChange={(event) => setDraft((prev) => ({ ...prev, address: event.target.value }))} /></DialogField><div className="md:col-span-2"><DialogField label={t('crmWorkspace.customers.note')}><textarea className={`${inputClass} min-h-24 resize-y`} value={draft.note ?? ''} onChange={(event) => setDraft((prev) => ({ ...prev, note: event.target.value }))} /></DialogField></div></div><div className="mt-6 flex justify-end gap-3"><button type="button" onClick={onClose} className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/10">{t('crmWorkspace.actions.cancel')}</button><button type="button" disabled={isSaving || !draft.name.trim()} onClick={() => onSave({ ...draft, name: draft.name.trim() })} className="inline-flex items-center gap-2 rounded-xl bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:opacity-50">{isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}{t('crmWorkspace.actions.save')}</button></div></div></div>;
};

const DialogField: React.FC<{ label: string; children: ReactNode }> = ({ label, children }) => <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-300">{label}</span>{children}</label>;

const QuoteDetailDrawer: React.FC<{ quote: CrmQuoteDetail | null; customers: CrmCustomer[]; isLoading: boolean; onClose: () => void; onStatus: (status: CrmQuoteStatus) => void; onCustomer: (customerId: number | null) => void; onShare: () => void; onPdf: (quote: CrmQuoteDetail) => void; busy: boolean }> = ({ quote, customers, isLoading, onClose, onStatus, onCustomer, onShare, onPdf, busy }) => {
  const { t } = useTranslation();
  if (!quote && !isLoading) return null;
  return <div className="fixed inset-0 z-[70] flex justify-end bg-slate-950/70 backdrop-blur-sm" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}><aside className="h-full w-full max-w-2xl overflow-y-auto border-l border-white/10 bg-slate-950 shadow-2xl shadow-black/60">{isLoading || !quote ? <div className="flex h-full items-center justify-center"><Loader2 className="h-7 w-7 animate-spin text-cyan-300" /></div> : <div className="p-5 md:p-7"><div className="flex items-start justify-between gap-4"><div><div className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs text-cyan-300">{quote.number}</span><StatusBadge status={quote.status} kind="quote" /></div><h2 className="mt-3 text-2xl font-semibold text-white">{quote.title}</h2><p className="mt-2 text-sm text-slate-400">{quote.customer?.name ?? t('crmWorkspace.quotes.noCustomer')}</p></div><button type="button" onClick={onClose} className="rounded-xl border border-white/10 bg-white/5 p-2.5 text-slate-300 hover:bg-white/10"><X className="h-5 w-5" /></button></div><div className="mt-6 grid grid-cols-2 gap-3"><div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-4"><p className="text-xs text-cyan-200">{t('crmWorkspace.quotes.amount')}</p><p className="mt-2 text-2xl font-semibold text-white">{makeCurrencyFormatter(quote.currency).format(quote.current_version.grand_total)}</p></div><div className="rounded-2xl border border-white/10 bg-white/5 p-4"><p className="text-xs text-slate-400">{t('crmWorkspace.quotes.validUntil')}</p><p className="mt-2 text-lg font-semibold text-white">{formatDate(quote.valid_until)}</p></div></div><div className="mt-5 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]"><label><span className="mb-1.5 block text-xs font-medium text-slate-400">{t('crmWorkspace.quotes.customer')}</span><select className={`${inputClass} py-2`} value={quote.customer_id ?? ''} disabled={busy} onChange={(event) => onCustomer(event.target.value ? Number(event.target.value) : null)}><option value="">{t('crmWorkspace.quotes.noCustomer')}</option>{customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name}{customer.inn ? ` · ${customer.inn}` : ''}</option>)}</select></label><div className="flex flex-wrap items-end gap-2"><StatusSelect value={quote.status} options={QUOTE_TRANSITIONS[quote.status]} label={(status) => t(`crmWorkspace.status.quote.${status}`)} onChange={onStatus} disabled={busy} /><button type="button" onClick={() => onPdf(quote)} disabled={!quote.current_version.html_content} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-200 hover:bg-white/10 disabled:opacity-35"><CloudDownload className="h-4 w-4" />{t('crmWorkspace.actions.pdf')}</button><button type="button" onClick={onShare} disabled={busy || !quote.current_version.html_content} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-200 hover:bg-white/10 disabled:opacity-35"><Copy className="h-4 w-4" />{t('crmWorkspace.actions.share')}</button></div></div><section className="mt-7"><div className="flex items-center justify-between"><h3 className="font-semibold text-white">{t('crmWorkspace.quotes.positionsTitle')}</h3><span className="text-xs text-slate-500">v{quote.current_version.version_number}</span></div><div className="mt-3 space-y-2">{quote.current_version.lines.map((line) => <div key={line.id} className="rounded-xl border border-white/10 bg-white/[0.035] p-4"><div className="flex items-start justify-between gap-4"><div><p className="font-medium text-white">{line.position}. {line.title}</p>{line.details.length > 0 && <p className="mt-1 text-xs leading-5 text-slate-400">{line.details.join(' · ')}</p>}</div><p className="shrink-0 text-sm font-semibold text-white">{makeCurrencyFormatter(quote.currency).format(line.total_price)}</p></div><p className="mt-2 text-xs text-slate-500">{line.quantity} × {makeCurrencyFormatter(quote.currency).format(line.unit_price)}</p></div>)}</div></section><section className="mt-7"><h3 className="font-semibold text-white">{t('crmWorkspace.quotes.history')}</h3><div className="mt-3 space-y-3 border-l border-white/10 pl-4">{quote.events.slice().reverse().map((event) => <div key={event.id} className="relative"><span className="absolute -left-[1.3rem] top-1.5 h-2 w-2 rounded-full bg-cyan-300" /><p className="text-sm text-slate-200">{t(`crmWorkspace.events.${event.event_type}`)}</p><p className="mt-0.5 text-xs text-slate-500">{formatDate(event.created_at)}</p></div>)}</div></section>{quote.versions.length > 1 && <section className="mt-7"><h3 className="font-semibold text-white">{t('crmWorkspace.quotes.versions')}</h3><div className="mt-3 flex flex-wrap gap-2">{quote.versions.map((version) => <span key={version.id} className={`rounded-xl border px-3 py-2 text-xs ${version.id === quote.current_version.id ? 'border-cyan-400/25 bg-cyan-400/10 text-cyan-100' : 'border-white/10 bg-white/5 text-slate-300'}`}>v{version.version_number} · {makeCurrencyFormatter(quote.currency).format(version.grand_total)}</span>)}</div></section>}</div>}</aside></div>;
};
