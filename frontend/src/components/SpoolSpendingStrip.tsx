import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { spoolsAPI, type SpoolSpendingCurrency, type SpoolSpendingGroup } from '../api/client';
import { currencySymbol } from '../utils/currency';
import { formatMonthLabel } from '../utils/monthLabel';
import { spoolQueryKeys } from '../utils/spoolQueries';

function formatMoney(amount: number, currency: string | null, language: string): string {
  const rounded = Math.abs(amount) >= 100 ? Math.round(amount) : Math.round(amount * 100) / 100;
  const symbol = currency ? currencySymbol(currency) : '?';
  return `${rounded.toLocaleString(language)} ${symbol}`;
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="truncate text-[11px] text-gray-400">{label}</p>
      <p className="text-base font-semibold text-white">{value}</p>
    </div>
  );
}

function GroupTable({
  title,
  rows,
  language,
  unlinkedLabel,
  perKgLabel,
  catalogLabel,
}: {
  title: string;
  rows: SpoolSpendingGroup[];
  language: string;
  unlinkedLabel: string;
  perKgLabel: string;
  catalogLabel: string;
}) {
  if (rows.length === 0) return null;
  return (
    <div className="min-w-0">
      <p className="mb-1.5 text-xs font-semibold text-gray-300">{title}</p>
      <div className="space-y-1">
        {rows.map((row) => (
          <div key={`${row.key ?? 'unlinked'}-${row.currency ?? 'none'}`}
            className="flex items-baseline justify-between gap-3 text-xs">
            <span className="min-w-0 truncate text-gray-300">{row.key ?? unlinkedLabel}</span>
            <span className="shrink-0 text-right text-gray-400">
              <span className="text-white">{formatMoney(row.bought_total, row.currency, language)}</span>
              {row.price_per_kg != null && (
                <span> · {formatMoney(row.price_per_kg, row.currency, language)}/{perKgLabel}</span>
              )}
              {row.catalog_price_per_kg != null && (
                <span className="text-gray-500"> ({catalogLabel} {formatMoney(row.catalog_price_per_kg, row.currency, language)})</span>
              )}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function SpoolSpendingStrip({ userId }: { userId: number | undefined }) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const query = useQuery({
    queryKey: [...spoolQueryKeys.root, 'spending', userId],
    queryFn: () => spoolsAPI.spending(12),
    staleTime: 60_000,
    enabled: userId !== undefined,
  });
  const data = query.data;
  if (!data || data.unpriced.spools_total === 0) return null;
  const language = i18n.language;
  const thisMonth = data.by_month[data.by_month.length - 1];
  const monthByCurrency = new Map(
    (thisMonth?.currencies ?? []).map((row) => [row.currency ?? '', row]),
  );
  const rows: SpoolSpendingCurrency[] = data.currencies;
  const { unpriced } = data;
  const caveats: string[] = [];
  if (unpriced.spools_without_price > 0) {
    caveats.push(t('spoolSpending.unpriced', {
      count: unpriced.spools_without_price,
      total: unpriced.spools_total,
    }));
  }
  if (rows.some((row) => row.currency === null && row.bought_count > 0)) {
    caveats.push(t('spoolSpending.currencyUnknown'));
  }
  if (unpriced.consumed_grams_without_price > 0) {
    caveats.push(t('spoolSpending.consumedUnpriced', {
      grams: Math.round(unpriced.consumed_grams_without_price),
    }));
  }
  if (unpriced.unreconciled_grams > 0) {
    caveats.push(t('spoolSpending.unreconciled', { grams: Math.round(unpriced.unreconciled_grams) }));
  }

  return (
    <section className="rounded-xl border border-white/10 bg-white/5 px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <h4 className="text-sm font-semibold text-white">{t('spoolSpending.title')}</h4>
        <button type="button" onClick={() => setOpen((prev) => !prev)}
          className="inline-flex items-center gap-1 text-xs text-purple-300 transition-colors hover:text-purple-200">
          {open ? t('spoolSpending.hide') : t('spoolSpending.details')}
          {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      </div>
      <div className="mt-2 space-y-2">
        {rows.map((row) => {
          const month = monthByCurrency.get(row.currency ?? '');
          return (
            <div key={row.currency ?? 'none'} className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
              <Figure label={t('spoolSpending.boughtMonth')}
                value={formatMoney(month?.bought_total ?? 0, row.currency, language)} />
              <Figure label={t('spoolSpending.consumedMonth')}
                value={formatMoney(month?.consumed_value ?? 0, row.currency, language)} />
              <Figure label={t('spoolSpending.shelf')}
                value={formatMoney(row.shelf_value, row.currency, language)} />
              <Figure label={t('spoolSpending.boughtYear')}
                value={formatMoney(row.bought_total, row.currency, language)} />
            </div>
          );
        })}
      </div>
      {caveats.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-[11px] text-amber-200/80">
          {caveats.map((text) => <li key={text}>{text}</li>)}
        </ul>
      )}
      {open && (
        <div className="mt-3 grid gap-4 border-t border-white/10 pt-3 lg:grid-cols-2">
          <GroupTable title={t('spoolSpending.byBrand')} rows={data.by_brand} language={language}
            unlinkedLabel={t('spoolSpending.unlinked')} perKgLabel={t('common.unitKilogram')}
            catalogLabel={t('spoolSpending.catalog')} />
          <GroupTable title={t('spoolSpending.byMaterial')} rows={data.by_material} language={language}
            unlinkedLabel={t('spoolSpending.unlinked')} perKgLabel={t('common.unitKilogram')}
            catalogLabel={t('spoolSpending.catalog')} />
          <div className="min-w-0 lg:col-span-2">
            <p className="mb-1.5 text-xs font-semibold text-gray-300">{t('spoolSpending.byMonth')}</p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3 lg:grid-cols-4">
              {[...data.by_month].reverse().filter((item) => item.currencies.length > 0).map((item) => (
                <div key={item.month} className="flex items-baseline justify-between gap-2">
                  <span className="text-gray-400">{formatMonthLabel(item.month, language)}</span>
                  <span className="text-white">
                    {item.currencies.map((row) => formatMoney(row.bought_total, row.currency, language)).join(' · ')}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
