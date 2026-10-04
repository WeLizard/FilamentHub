export const numberInputResetClass =
  '[appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none';

/** Numeric field with a unit badge (currency, rate, hours); the calculator's standard money input. */
export const InputWithSuffix: React.FC<{
  value: number;
  onChange: (value: number) => void;
  placeholder: string;
  suffix: string;
  step?: string;
}> = ({ value, onChange, placeholder, suffix, step }) => (
  <div className="flex w-full items-center gap-2 rounded-2xl border border-white/10 bg-slate-950/60 pr-3 transition-all focus-within:border-transparent focus-within:ring-2 focus-within:ring-cyan-400/60 sm:max-w-[15rem]">
    <input
      type="number"
      className={`${numberInputResetClass} w-full min-w-0 bg-transparent px-4 py-3 text-white placeholder:text-slate-500 focus:outline-none`}
      value={value || ''}
      placeholder={placeholder}
      step={step}
      onChange={(event) => onChange(Number(event.target.value) || 0)}
    />
    <span className="pointer-events-none shrink-0 rounded-xl border border-white/[0.08] bg-white/[0.06] px-2.5 py-1 text-xs font-medium text-slate-300">
      {suffix}
    </span>
  </div>
);
