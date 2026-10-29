import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { crmAPI } from '../api/client';
import { formatMonthLabel } from '../utils/monthLabel';

function formatAmounts(amounts: Record<string, number>, language: string): string {
  const entries = Object.entries(amounts).filter(([, value]) => value !== 0);
  if (entries.length === 0) return '0';
  return entries.map(([currency, value]) => {
    try {
      return new Intl.NumberFormat(language, { style: 'currency', currency, maximumFractionDigits: 0 }).format(value);
    } catch {
      return `${Math.round(value).toLocaleString(language)} ${currency}`;
    }
  }).join(' · ');
}

export function RevenueStrip({ userId }: { userId: number | undefined }) {
  const { t, i18n } = useTranslation();
  const query = useQuery({
    queryKey: ['crm', 'summary', userId],
    queryFn: () => crmAPI.getSummary(),
    staleTime: 60_000,
    enabled: userId !== undefined,
  });
  const summary = query.data;
  const months = (summary?.revenue_by_month ?? []).filter((item) => Object.keys(item.amounts).length > 0);
  if (!summary || months.length === 0) return null;
  return (
    <section className="rounded-xl border border-white/10 bg-white/5 px-4 py-3">
      <h4 className="text-sm font-semibold text-white">{t('revenueStrip.title')}</h4>
      <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        <div className="min-w-0">
          <p className="truncate text-[11px] text-gray-400">{t('revenueStrip.thisMonth')}</p>
          <p className="text-base font-semibold text-white">{formatAmounts(summary.revenue_month, i18n.language)}</p>
        </div>
        {[...months].reverse().slice(0, 3).map((item) => (
          <div key={item.month} className="min-w-0">
            <p className="truncate text-[11px] text-gray-400">{formatMonthLabel(item.month, i18n.language)}</p>
            <p className="text-base font-semibold text-white">{formatAmounts(item.amounts, i18n.language)}</p>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[11px] text-gray-500">{t('revenueStrip.note')}</p>
    </section>
  );
}
