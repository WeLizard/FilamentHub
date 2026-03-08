/**
 * Страница Калькулятора стоимости 3D-печати.
 * Пока это UI-слой, поэтому оболочка должна нормально жить и в route, и внутри ProfilePage.
 */

import { type ReactNode, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Calculator, Upload, FileText, Save, Download, Trash2, Clock, DollarSign, Weight, Printer } from 'lucide-react';

const surfaceClass = 'relative overflow-hidden rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.88),rgba(15,23,42,0.72))] shadow-[0_30px_90px_-50px_rgba(15,23,42,0.95)] backdrop-blur-xl';
const inputClass = 'w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-400/60 focus:border-transparent transition-all';
const ghostButtonClass = 'inline-flex items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-white transition-all hover:bg-white/10';

export const CalculatorPage: React.FC = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'calculator' | 'history'>('calculator');

  return (
    <div className="space-y-6">
      <section className={`${surfaceClass} p-0`}>
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.18),transparent_34%),radial-gradient(circle_at_85%_18%,rgba(168,85,247,0.28),transparent_38%),radial-gradient(circle_at_50%_120%,rgba(59,130,246,0.16),transparent_42%)]" />
        <div className="relative px-6 py-7 md:px-8 md:py-8">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-3xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-200">
                Calculator Pro
              </div>
              <div className="mt-4 flex items-start gap-4">
                <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-[1.4rem] border border-white/10 bg-white/10 shadow-[inset_0_1px_0_rgba(255,255,255,0.15)]">
                  <Calculator className="h-8 w-8 text-cyan-300" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-white md:text-4xl">
                    {t('calculator.title')}
                  </h1>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300 md:text-base">
                    {t('calculator.subtitle')}
                  </p>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:min-w-[18rem]">
              <MetricTile label={t('calculator.totalCost')} value="0.00 ₽" />
              <MetricTile label={t('calculator.tabs.history')} value="0" />
            </div>
          </div>

          <div className="mt-6 inline-flex flex-wrap gap-2 rounded-[1.4rem] border border-white/10 bg-black/20 p-1.5">
            <TabButton
              active={activeTab === 'calculator'}
              icon={<Calculator className="h-4 w-4" />}
              label={t('calculator.tabs.calculator')}
              onClick={() => setActiveTab('calculator')}
            />
            <TabButton
              active={activeTab === 'history'}
              icon={<Clock className="h-4 w-4" />}
              label={t('calculator.tabs.history')}
              badge="0"
              onClick={() => setActiveTab('history')}
            />
          </div>
        </div>
      </section>

      {activeTab === 'calculator' ? <CalculatorView /> : <HistoryView />}
    </div>
  );
};

/** View: Калькулятор (основная форма) */
const CalculatorView: React.FC = () => {
  const { t } = useTranslation();

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(20rem,0.9fr)]">
      <div className="space-y-5">
        <SurfaceCard className="p-6 md:p-7">
          <SectionHeading icon={<Upload className="h-5 w-5 text-cyan-300" />} title={t('calculator.uploadGcode')} />
          <div className="mt-5 rounded-[1.6rem] border border-dashed border-cyan-400/30 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.14),transparent_52%),linear-gradient(180deg,rgba(15,23,42,0.8),rgba(2,6,23,0.85))] p-8 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] transition-all hover:border-cyan-300/50 md:p-10">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-[1.35rem] border border-white/10 bg-white/5">
              <Upload className="h-7 w-7 text-cyan-300" />
            </div>
            <p className="mt-5 text-base font-semibold text-white">{t('calculator.dragDropGcode')}</p>
            <p className="mt-2 text-sm text-slate-300">{t('calculator.orClickToSelect')}</p>
            <p className="mt-3 text-xs uppercase tracking-[0.18em] text-slate-500">{t('calculator.supportedFormats')}</p>
          </div>
        </SurfaceCard>

        <SurfaceCard className="p-6 md:p-7">
          <SectionHeading icon={<Weight className="h-5 w-5 text-cyan-300" />} title={t('calculator.materialSection')} />
          <div className="mt-5 space-y-5">
            <FieldBlock label={t('calculator.selectMaterial')}>
              <select className={inputClass} defaultValue="">
                <option value="">{t('calculator.chooseFromCatalog')}</option>
              </select>
            </FieldBlock>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <FieldBlock label={t('calculator.partWeight')}>
                <InputWithSuffix placeholder="0" suffix={t('calculator.grams')} />
              </FieldBlock>
              <FieldBlock label={t('calculator.supportsWeight')}>
                <InputWithSuffix placeholder="0" suffix={t('calculator.grams')} />
              </FieldBlock>
              <FieldBlock label={t('calculator.spoolPrice')}>
                <InputWithSuffix placeholder="0" suffix="₽" />
              </FieldBlock>
              <FieldBlock label={t('calculator.spoolWeight')}>
                <InputWithSuffix placeholder="1" suffix={t('calculator.kg')} step="0.1" />
              </FieldBlock>
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard className="p-6 md:p-7">
          <SectionHeading icon={<Clock className="h-5 w-5 text-cyan-300" />} title={t('calculator.printTimeSection')} />
          <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <FieldBlock label={t('calculator.hours')}>
              <input type="number" className={inputClass} placeholder="0" />
            </FieldBlock>
            <FieldBlock label={t('calculator.minutes')}>
              <input type="number" className={inputClass} placeholder="0" />
            </FieldBlock>
            <FieldBlock label={t('calculator.seconds')}>
              <input type="number" className={inputClass} placeholder="0" />
            </FieldBlock>
          </div>
        </SurfaceCard>

        <SurfaceCard className="p-6 md:p-7">
          <SectionHeading icon={<DollarSign className="h-5 w-5 text-cyan-300" />} title={t('calculator.ratesSection')} />
          <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
            <FieldBlock label={t('calculator.printingRate')}>
              <InputWithSuffix placeholder="170" suffix={`₽/${t('calculator.hourAbbr')}`} />
            </FieldBlock>
            <FieldBlock label={t('calculator.electricityCost')}>
              <InputWithSuffix placeholder="6" suffix={`₽/${t('calculator.kwhAbbr')}`} />
            </FieldBlock>
            <FieldBlock label={t('calculator.quantity')}>
              <input type="number" className={inputClass} placeholder="1" min="1" />
            </FieldBlock>
            <FieldBlock label={t('calculator.printerPower')}>
              <InputWithSuffix placeholder="350" suffix={t('calculator.wattAbbr')} />
            </FieldBlock>
          </div>
        </SurfaceCard>

        <button className="inline-flex w-full items-center justify-center gap-2 rounded-[1.6rem] bg-[linear-gradient(135deg,#0891b2,#7c3aed)] px-6 py-4 text-base font-semibold text-white shadow-[0_18px_35px_-18px_rgba(6,182,212,0.7)] transition-all hover:translate-y-[-1px] hover:shadow-[0_22px_42px_-18px_rgba(124,58,237,0.72)]">
          <Calculator className="h-5 w-5" />
          {t('calculator.calculateButton')}
        </button>
      </div>

      <div className="xl:pt-1">
        <SurfaceCard className="p-6 md:p-7 xl:sticky xl:top-8">
          <div className="flex items-center justify-between gap-4">
            <SectionHeading icon={<Calculator className="h-5 w-5 text-cyan-300" />} title={t('calculator.resultsTitle')} compact />
            <div className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-cyan-200">
              {t('calculator.perPart')}
            </div>
          </div>

          <div className="mt-6 overflow-hidden rounded-[1.7rem] border border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.18),transparent_45%),linear-gradient(145deg,rgba(14,116,144,0.2),rgba(76,29,149,0.26))] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-300">{t('calculator.totalCost')}</p>
            <p className="mt-3 text-4xl font-bold tracking-tight text-white">0.00 ₽</p>
            <p className="mt-2 text-sm text-slate-300">
              {t('calculator.perPart')}: <span className="text-white">0.00 ₽</span>
            </p>
          </div>

          <div className="mt-6 divide-y divide-white/10 overflow-hidden rounded-[1.6rem] border border-white/[0.08] bg-black/20">
            <MetricRow label={t('calculator.material')} value="0.00 ₽" />
            <MetricRow label={t('calculator.electricity')} value="0.00 ₽" />
            <MetricRow label={t('calculator.printing')} value="0.00 ₽" />
            <MetricRow label={t('calculator.overhead')} value="0.00 ₽" />
            <MetricRow label={t('calculator.markup')} value="0.00 ₽" />
          </div>

          <div className="mt-6 space-y-3">
            <button className={`${ghostButtonClass} w-full`}>
              <Save className="h-4 w-4" />
              {t('calculator.saveToHistory')}
            </button>
            <button className={`${ghostButtonClass} w-full`}>
              <FileText className="h-4 w-4" />
              {t('calculator.generateQuote')}
            </button>
          </div>

          <div className="mt-6 rounded-[1.45rem] border border-amber-400/20 bg-amber-400/[0.08] p-4">
            <div className="flex items-start gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-amber-300/15 bg-black/20">
                <Printer className="h-5 w-5 text-amber-300" />
              </div>
              <div>
                <p className="text-sm font-medium text-white">{t('calculator.printTimeEstimate')}</p>
                <p className="mt-1 text-xs leading-5 text-slate-300">{t('calculator.basedOnGcode')}</p>
              </div>
            </div>
          </div>
        </SurfaceCard>
      </div>
    </div>
  );
};

/** View: История расчётов */
const HistoryView: React.FC = () => {
  const { t } = useTranslation();

  return (
    <SurfaceCard className="p-6 md:p-7">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <SectionHeading icon={<Clock className="h-5 w-5 text-cyan-300" />} title={t('calculator.historyTitle')} compact />
        <div className="flex flex-col gap-2 sm:flex-row">
          <button className={ghostButtonClass}>
            <Download className="h-4 w-4" />
            {t('calculator.export')}
          </button>
          <button className="inline-flex items-center justify-center gap-2 rounded-2xl border border-red-400/25 bg-red-500/10 px-4 py-3 text-sm font-medium text-red-200 transition-all hover:bg-red-500/15">
            <Trash2 className="h-4 w-4" />
            {t('calculator.deleteSelected')}
          </button>
        </div>
      </div>

      <div className="mt-6 rounded-[1.8rem] border border-dashed border-white/12 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.08),transparent_44%),linear-gradient(180deg,rgba(2,6,23,0.35),rgba(2,6,23,0.62))] px-6 py-16 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
        <div className="mx-auto flex h-[4.5rem] w-[4.5rem] items-center justify-center rounded-[1.6rem] border border-white/10 bg-white/5">
          <Clock className="h-9 w-9 text-slate-500" />
        </div>
        <h2 className="mt-6 text-2xl font-semibold text-white">{t('calculator.noHistory')}</h2>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-300">
          {t('calculator.noHistoryDescription')}
        </p>
        <button className="mt-8 inline-flex items-center justify-center rounded-[1.3rem] bg-[linear-gradient(135deg,#0891b2,#7c3aed)] px-6 py-3 text-sm font-semibold text-white shadow-[0_18px_35px_-18px_rgba(6,182,212,0.7)] transition-all hover:translate-y-[-1px]">
          {t('calculator.createFirstCalculation')}
        </button>
      </div>
    </SurfaceCard>
  );
};

const SurfaceCard: React.FC<{ children: ReactNode; className?: string }> = ({ children, className = '' }) => (
  <section className={`${surfaceClass} ${className}`}>
    <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.06),transparent_40%)]" />
    <div className="relative">{children}</div>
  </section>
);

const SectionHeading: React.FC<{ icon: ReactNode; title: string; compact?: boolean }> = ({
  icon,
  title,
  compact = false,
}) => (
  <div className="flex items-center gap-3">
    <div className={`flex items-center justify-center rounded-[1.1rem] border border-white/10 bg-white/[0.06] ${compact ? 'h-10 w-10' : 'h-11 w-11'}`}>
      {icon}
    </div>
    <h2 className={`${compact ? 'text-lg' : 'text-xl'} font-semibold text-white`}>{title}</h2>
  </div>
);

const FieldBlock: React.FC<{ label: string; children: ReactNode }> = ({ label, children }) => (
  <label className="block">
    <span className="mb-2 block text-sm font-medium text-slate-300">{label}</span>
    {children}
  </label>
);

const InputWithSuffix: React.FC<{ placeholder: string; suffix: string; step?: string }> = ({
  placeholder,
  suffix,
  step,
}) => (
  <div className="relative">
    <input type="number" className={`${inputClass} pr-20`} placeholder={placeholder} step={step} />
    <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded-xl border border-white/[0.08] bg-white/[0.06] px-2.5 py-1 text-xs font-medium text-slate-300">
      {suffix}
    </span>
  </div>
);

const MetricTile: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-[1.45rem] border border-white/10 bg-white/5 px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">{label}</p>
    <p className="mt-2 text-2xl font-semibold tracking-tight text-white">{value}</p>
  </div>
);

const MetricRow: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
    <span className="text-slate-400">{label}</span>
    <span className="font-medium text-white">{value}</span>
  </div>
);

const TabButton: React.FC<{
  active: boolean;
  icon: ReactNode;
  label: string;
  badge?: string;
  onClick: () => void;
}> = ({ active, icon, label, badge, onClick }) => (
  <button
    onClick={onClick}
    className={`inline-flex items-center gap-2 rounded-[1.1rem] px-4 py-2.5 text-sm font-medium transition-all ${
      active
        ? 'bg-white text-slate-950 shadow-[0_12px_28px_-18px_rgba(255,255,255,0.9)]'
        : 'text-slate-300 hover:bg-white/[0.08] hover:text-white'
    }`}
  >
    {icon}
    <span>{label}</span>
    {badge ? (
      <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${active ? 'bg-slate-950/10 text-slate-700' : 'bg-white/10 text-slate-300'}`}>
        {badge}
      </span>
    ) : null}
  </button>
);
