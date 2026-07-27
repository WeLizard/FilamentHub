import { useTranslation } from 'react-i18next';

interface QuickPicksProps {
  options: { label: string; value: number }[];
  value: number;
  onPick: (value: number) => void;
  hint?: boolean;
  caption?: string;
}

export const QuickPicks: React.FC<QuickPicksProps> = ({
  options,
  value,
  onPick,
  hint = true,
  caption,
}) => {
  const { t } = useTranslation();

  return (
    <div className="mt-1.5">
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => (
          <button
            key={option.label}
            type="button"
            onClick={() => onPick(option.value)}
            className={`rounded-full border px-2 py-1 text-[11px] transition ${
              value === option.value
                ? 'border-cyan-400/50 bg-cyan-500/15 text-cyan-200'
                : 'border-white/10 bg-slate-950/40 text-slate-400 hover:border-white/20 hover:text-slate-200'
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
      {caption ? (
        <p className="mt-1 text-[11px] leading-4 text-slate-500">{caption}</p>
      ) : null}
      {hint ? (
        <p className="mt-1 text-[11px] leading-4 text-slate-500">
          {t('profilePage.calculator.quickPickHint')}
        </p>
      ) : null}
    </div>
  );
};
