import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';

import type { CatalogImportSheet } from '../../../types/api';
import { FILAMENT_COLOR_GROUPS, FILAMENT_COLOR_GROUP_PALETTE } from '../../../utils/filamentColorGroups';
import { cellText, isTruthyCell, listValues, numberFromInput, settledNumber } from '../../../utils/catalogProposalEdit';
import { Dropdown } from '../../Dropdown';
import { FloatingHSLColorPicker } from '../../FloatingHSLColorPicker';
import { LinkListEditor } from '../../LinkListEditor';
import { fieldSpec } from './fieldSpecs';

export const inputClass = 'h-9 w-full rounded-lg border border-white/15 bg-slate-950/70 px-2.5 text-sm text-white placeholder:text-gray-500 focus:border-indigo-400 focus:outline-none disabled:opacity-60';
const HEX = /^#(?:[\da-f]{3}|[\da-f]{6})$/i;
const MAX_COLORS = 5;

interface ColorSwatchProps {
  value: string;
  disabled: boolean;
  label: string;
  onChange: (hex: string) => void;
}

function ColorSwatch({ value, disabled, label, onChange }: ColorSwatchProps) {
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLButtonElement>(null);
  const valid = HEX.test(value);
  return (
    <span className="relative inline-flex shrink-0">
      <button ref={anchor} type="button" disabled={disabled} aria-label={label}
        onClick={(event) => { event.stopPropagation(); setOpen((current) => !current); }}
        className="h-9 w-9 rounded-lg border border-white/30 transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-60"
        style={{ backgroundColor: valid ? value : 'transparent' }} />
      <FloatingHSLColorPicker anchorElement={anchor.current} color={valid ? value : '#FF0000'} isOpen={open}
        onChange={onChange} onToggle={setOpen} />
    </span>
  );
}

interface TextEntryProps {
  value: unknown;
  disabled: boolean;
  label: string;
  onChange: (value: unknown) => void;
}

/** Keeps what is being typed ("1.0", "0.") until the field is left; only then does it settle on a number. */
function NumberEntry({ value, disabled, label, onChange }: TextEntryProps) {
  const [typed, setTyped] = useState<string | null>(null);
  return <input aria-label={label} disabled={disabled} inputMode="decimal" value={typed ?? cellText(value)}
    onChange={(event) => { setTyped(event.target.value); onChange(numberFromInput(event.target.value)); }}
    onBlur={() => {
      if (typed === null) return;
      const settled = settledNumber(typed);
      if (settled !== value) onChange(settled);
      setTyped(null);
    }} className={inputClass} />;
}

/** Objects and arrays are edited as JSON; text that does not parse is never stored, only flagged. */
function JsonEntry({ value, disabled, label, onChange }: TextEntryProps) {
  const { t } = useTranslation();
  const [typed, setTyped] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);
  return <div>
    <textarea aria-label={label} disabled={disabled} value={typed ?? cellText(value)} rows={2}
      aria-invalid={invalid || undefined}
      onChange={(event) => {
        setTyped(event.target.value);
        try {
          const parsed: unknown = JSON.parse(event.target.value);
          if (parsed === null || typeof parsed !== 'object') throw new Error('Not an object');
          setInvalid(false);
          onChange(parsed);
        } catch { setInvalid(true); }
      }}
      onBlur={() => { if (!invalid) setTyped(null); }}
      className="w-full rounded-lg border border-white/15 bg-slate-950/70 px-2.5 py-2 font-mono text-xs text-white focus:border-indigo-400 focus:outline-none disabled:opacity-60" />
    {invalid && <p role="alert" className="mt-1 text-xs text-red-300">{t('adminCatalogImport.curation.invalidJson')}</p>}
  </div>;
}

interface ProposalFieldControlProps {
  sheet: CatalogImportSheet;
  field: string;
  value: unknown;
  disabled: boolean;
  /** Accessible name and the base for per-item names. */
  label: string;
  onChange: (value: unknown) => void;
}

/** One control per value kind; it only ever calls onChange from a user action. */
export function ProposalFieldControl({ sheet, field, value, disabled, label, onChange }: ProposalFieldControlProps) {
  const { t } = useTranslation();
  const spec = fieldSpec(sheet, field);
  const text = cellText(value);

  switch (spec.kind) {
    case 'bool':
      return <input type="checkbox" aria-label={label} disabled={disabled}
        checked={isTruthyCell(value, field === 'enabled')} onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 accent-purple-500" />;
    case 'select':
    case 'availability':
    case 'marketAvailability': {
      const codes = [...(spec.options ?? [])];
      if (text && !codes.includes(text)) codes.push(text);
      return <Dropdown size="sm" clearable={false} value={text} disabled={disabled}
        options={codes.map((code) => ({
          value: code,
          label: t(`${spec.optionsKey}${code}`, { defaultValue: code }),
        }))}
        onChange={(next) => onChange(String(next))} />;
    }
    case 'colorGroup': {
      const codes: string[] = [...FILAMENT_COLOR_GROUPS];
      if (text && !codes.includes(text)) codes.push(text);
      return <Dropdown size="sm" clearable={false} value={text} disabled={disabled}
        options={codes.map((code) => ({
          value: code,
          label: t(`colorGroups.${code}`, { defaultValue: code }),
          icon: <span className="inline-block h-3 w-3 rounded-full border border-white/40"
            style={{ backgroundColor: FILAMENT_COLOR_GROUP_PALETTE[code as keyof typeof FILAMENT_COLOR_GROUP_PALETTE]?.[2] ?? 'transparent' }} />,
        }))}
        onChange={(next) => onChange(String(next))} />;
    }
    case 'colorHex':
      return <div className="flex items-center gap-1.5">
        <ColorSwatch value={text} disabled={disabled} label={label} onChange={onChange} />
        <input aria-label={`${label} #`} disabled={disabled} value={text} maxLength={9}
          onChange={(event) => onChange(event.target.value)} className={`${inputClass} min-w-0 font-mono`} />
      </div>;
    case 'colors': {
      const items = Array.isArray(value) ? value.map(cellText) : listValues(value);
      return <div className="flex flex-wrap items-center gap-2">
        {items.map((color, index) => <span key={index} className="inline-flex items-center gap-1">
          <ColorSwatch value={color} disabled={disabled} label={`${label} ${index + 1}`}
            onChange={(hex) => onChange(items.map((item, i) => i === index ? hex : item))} />
          <input aria-label={`${label} ${index + 1} #`} disabled={disabled} value={color} maxLength={9}
            onChange={(event) => onChange(items.map((item, i) => i === index ? event.target.value : item))}
            className={`${inputClass} w-24 font-mono`} />
          {!disabled && <button type="button" aria-label={`${t('adminCatalogImport.curation.removeListItem')} ${index + 1}`}
            onClick={() => onChange(items.filter((_, i) => i !== index))}
            className="flex h-9 w-7 items-center justify-center rounded-lg text-gray-400 hover:text-red-300">
            <X className="h-4 w-4" />
          </button>}
        </span>)}
        {!disabled && items.length < MAX_COLORS && <button type="button"
          onClick={() => onChange([...items, '#FFFFFF'])}
          className="h-9 rounded-lg border border-white/15 px-3 text-xs text-indigo-200 transition hover:bg-white/5">
          + {t('adminCatalogImport.curation.addColor')}
        </button>}
      </div>;
    }
    case 'social':
      return <LinkListEditor kind="social" value={value} disabled={disabled} label={label}
        onChange={(next) => onChange(next)} />;
    case 'shop':
      return <LinkListEditor kind="shop" value={value} disabled={disabled} label={label}
        onChange={(next) => onChange(next)} />;
    case 'number':
      return <NumberEntry value={value} disabled={disabled} label={label} onChange={onChange} />;
    case 'country':
      return <input aria-label={label} disabled={disabled} value={text} maxLength={2}
        onChange={(event) => onChange(event.target.value.toUpperCase())} className={`${inputClass} uppercase`} />;
    case 'textarea':
      return <textarea aria-label={label} disabled={disabled} value={text} rows={field === 'description' ? 3 : 2}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border border-white/15 bg-slate-950/70 px-2.5 py-2 text-sm text-white placeholder:text-gray-500 focus:border-indigo-400 focus:outline-none disabled:opacity-60" />;
    default:
      if (value !== null && typeof value === 'object') {
        return <JsonEntry value={value} disabled={disabled} label={label} onChange={onChange} />;
      }
      return <input aria-label={label} disabled={disabled} value={text}
        onChange={(event) => onChange(event.target.value)} className={inputClass} />;
  }
}
