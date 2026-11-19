import type { LucideIcon } from 'lucide-react';

export interface SegmentedToggleOption<T extends string> {
  value: T;
  label: string;
  icon: LucideIcon;
}

interface SegmentedToggleProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: readonly SegmentedToggleOption<T>[];
  ariaLabel?: string;
  /** Show the text next to each icon; otherwise the label is only a tooltip. */
  showLabels?: boolean;
  /** Tailwind classes that hide the labels below a breakpoint, e.g. "hidden sm:inline". */
  labelClassName?: string;
  className?: string;
}

/** A row of mutually exclusive buttons: one of two or three ways to show the same thing. */
export function SegmentedToggle<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
  showLabels = false,
  labelClassName = '',
  className = '',
}: SegmentedToggleProps<T>) {
  return (
    <div
      className={`flex items-center rounded-lg border border-white/20 bg-white/10 p-1 ${className}`}
      role="group"
      aria-label={ariaLabel}
    >
      {options.map(({ value: option, label, icon: Icon }) => (
        <button
          key={option}
          type="button"
          onClick={() => onChange(option)}
          className={`${showLabels ? 'inline-flex items-center gap-2 px-3 py-2' : 'p-2'} rounded transition-all ${
            value === option ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'
          }`}
          title={label}
          aria-label={showLabels ? undefined : label}
          aria-pressed={value === option}
        >
          <Icon className="h-4 w-4" aria-hidden />
          {showLabels && <span className={labelClassName}>{label}</span>}
        </button>
      ))}
    </div>
  );
}
