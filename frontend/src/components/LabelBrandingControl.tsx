import { useId } from "react";
import { useTranslation } from "react-i18next";
import type { LabelBrandingMode } from "../types/labels";

const modes: LabelBrandingMode[] = ["none", "mark", "full"];

export function LabelBrandingControl({
  label,
  value,
  onChange,
  markAvailable = true,
  disabled = false,
}: {
  label: string;
  value: LabelBrandingMode;
  onChange: (value: LabelBrandingMode) => void;
  markAvailable?: boolean;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const name = useId();
  return (
    <fieldset
      aria-label={label}
      disabled={disabled}
      className="min-w-0 disabled:opacity-50"
    >
      <div className="rounded-lg border border-white/15 bg-black/20 p-0.5">
        <div className="relative grid grid-cols-3">
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 left-0 w-1/3 rounded-md bg-cyan-300/20 transition-transform motion-reduce:transition-none"
            style={{ transform: `translateX(${modes.indexOf(value) * 100}%)` }}
          />
          {modes.map((mode) => {
            const unavailable = mode === "mark" && !markAvailable;
            return (
              <label
                key={mode}
                className={`relative min-w-0 ${disabled || unavailable ? "cursor-not-allowed" : "cursor-pointer"}`}
                title={
                  unavailable
                    ? t("labelStudio.brandLogoUnavailable")
                    : undefined
                }
              >
                <input
                  type="radio"
                  name={name}
                  value={mode}
                  checked={value === mode}
                  disabled={unavailable}
                  onChange={() => onChange(mode)}
                  className="peer sr-only"
                />
                <span className="flex h-full min-h-10 items-center justify-center rounded-md px-1 py-2 text-center text-xs leading-tight text-gray-300 peer-checked:text-cyan-100 peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-cyan-300 peer-disabled:opacity-40">
                  {t(`labelStudio.branding_${mode}`)}
                </span>
              </label>
            );
          })}
        </div>
      </div>
    </fieldset>
  );
}
