import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown } from 'lucide-react';

type Part = 'hotend' | 'bed' | 'steppers' | 'electronics';

interface PowerPartsBreakdownProps {
  hotend: number;
  bed: number;
  steppers: number;
  electronics: number;
  onChange: (part: Part, value: number) => void;
  onCommit?: (part: Part, value: number | null) => void;
}

const inputClass =
  'w-full max-w-[8rem] rounded-xl border border-white/10 bg-slate-950/60 px-3 py-1.5 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-400/60';

export const PowerPartsBreakdown: React.FC<PowerPartsBreakdownProps> = ({
  hotend,
  bed,
  steppers,
  electronics,
  onChange,
  onCommit,
}) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<Partial<Record<Part, string>>>({});
  const total = hotend + bed + steppers + electronics;

  const part = (name: Part, label: string, value: number) => (
    <label className="block">
      <span className="mb-1 block text-[11px] leading-4 text-slate-400">{label}</span>
      <input
        type="number"
        min="0"
        inputMode="decimal"
        className={inputClass}
        value={drafts[name] ?? String(value)}
        placeholder="0"
        onChange={(event) => {
          const rawValue = event.target.value;
          setDrafts((current) => ({ ...current, [name]: rawValue }));
          if (rawValue !== '') onChange(name, Math.max(0, Number(rawValue) || 0));
          else if (!onCommit) onChange(name, 0);
        }}
        onBlur={(event) => {
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
          {total > 0 ? (
            <p className="col-span-2 text-[11px] text-slate-500">
              {t('printerCost.powerSum', { value: total })}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};
