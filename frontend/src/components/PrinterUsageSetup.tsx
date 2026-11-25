import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Check } from 'lucide-react';
import type { PhysicalPrinter, PrinterUsageSetup as UsageSetup } from '../api/client';
import { USAGE_SETUP_STEPS, usageSetupProgress } from '../utils/printerUsageSetup';

interface PrinterUsageSetupProps {
  printer: PhysicalPrinter;
  setup: UsageSetup;
  onOpenConnection: () => void;
}

/** The next step until prints from this printer are deducted; nothing once they are. */
export function PrinterUsageSetup({ printer, setup, onOpenConnection }: PrinterUsageSetupProps) {
  const { t } = useTranslation();
  const progress = usageSetupProgress(printer, setup);
  if (!progress.applicable || progress.done.print || progress.current == null) return null;
  const { current } = progress;
  const hintKey = current === 'connect' && progress.nativeOnly
    ? 'printerUsageSetup.hint.connectMoonraker'
    : current === 'print' && progress.viaOrca
      ? 'printerUsageSetup.hint.printOrca'
      : `printerUsageSetup.hint.${current}`;
  const actionCls = 'text-amber-100 underline underline-offset-2 hover:text-white';

  return (
    <div className="rounded-lg border border-amber-400/20 bg-amber-400/[0.06] px-2.5 py-2 text-[11px] text-amber-100/80">
      <p className="font-medium text-amber-100">{t('printerUsageSetup.title')}</p>
      <ol className="mt-1.5 space-y-0.5">
        {USAGE_SETUP_STEPS.map((step) => (
          <li
            key={step}
            className={`flex items-center gap-1.5 ${
              progress.done[step] ? 'text-emerald-200/70' : step === current ? 'text-amber-100' : 'text-amber-100/40'
            }`}
          >
            {progress.done[step]
              ? <Check className="h-3 w-3 shrink-0" />
              : <span className="h-3 w-3 shrink-0 rounded-full border border-current" />}
            <span>{t(`printerUsageSetup.step.${step}`)}</span>
          </li>
        ))}
      </ol>
      <p className="mt-1.5">{t(hintKey)}</p>
      {current === 'connect' && (
        <button type="button" onClick={onOpenConnection} className={`mt-1 ${actionCls}`}>
          {t('printerSetup.connectionSettings')}
        </button>
      )}
      {(current === 'spools' || current === 'slot') && (
        <Link to="/profile?tab=spools" className={`mt-1 inline-block ${actionCls}`}>
          {t(`printerUsageSetup.action.${current}`)}
        </Link>
      )}
    </div>
  );
}
