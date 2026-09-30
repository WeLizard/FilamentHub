import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown } from 'lucide-react';

export type PowerPart = 'hotend' | 'bed' | 'steppers' | 'electronics';

interface PowerPartsBreakdownProps {
  hotend: number | null;
  bed: number | null;
  steppers: number | null;
  electronics: number | null;
  placeholders?: Partial<Record<PowerPart, number>>;
  onChange: (part: PowerPart, value: number) => void;
  onCommit?: (part: PowerPart, value: number | null) => void;
}

const inputClass =
  'w-full max-w-[8rem] rounded-xl border border-white/10 bg-slate-950/60 px-3 py-1.5 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-400/60';

export const PowerPartsBreakdown: React.FC<PowerPartsBreakdownProps> = ({
  hotend,
  bed,
  steppers,
  electronics,
  placeholders = {},
  onChange,
  onCommit,
}) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<Partial<Record<PowerPart, string>>>({});
  const parts = [hotend, bed, steppers, electronics];
  const total = parts.every((value) => value != null)
    ? parts.reduce<number>((sum, value) => sum + (value ?? 0), 0)
    : 0;

  const part = (name: PowerPart, label: string, value: number | null) => (
    <label className="block">
      <span className="mb-1 block text-[11px] leading-4 text-slate-400">{label}</span>
      <input
        type="number"
        min="0"
        inputMode="decimal"
        className={inputClass}
        value={drafts[name] ?? (value == null ? '' : String(value))}
        placeholder={placeholders[name] != null ? String(placeholders[name]) : '0'}
        onChange={(event) => {
          const rawValue = event.target.value;
          setDrafts((current) => ({ ...current, [name]: rawValue }));
          if (rawValue !== '') onChange(name, Math.max(0, Number(rawValue) || 0));
          else if (!onCommit) onChange(name, 0);
        }}
        onBlur={(event) => {
          if (drafts[name] === undefined) return;
          const rawValue = event.target.value;
          setDrafts((current) => {
            const next = { ...current };
            delete next[name];
            return next;
          });
          onCommit?.(name, rawValue === '' ? null : Math.max(0, Number(rawValue) || 0));
        }}
      />
    </label>
  );

  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex items-center gap-1 text-[11px] font-semibold text-cyan-300"
      >
        {t('printerCost.powerBreakdown')}
        <ChevronDown className={`h-3 w-3 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open ? (
        <div className="mt-2 grid grid-cols-2 gap-2">
          {part('hotend', t('printerCost.powerHotend'), hotend)}
          {part('bed', t('printerCost.powerBed'), bed)}
          {part('steppers', t('printerCost.powerSteppers'), steppers)}
          {part('electronics', t('printerCost.powerElectronics'), electronics)}
          <p className="col-span-2 text-[11px] leading-4 text-slate-500">
            {total > 0 ? t('printerCost.powerSum', { value: total }) : t('printerCost.powerPartsHint')}
          </p>
        </div>
      ) : null}
    </div>
  );
};
