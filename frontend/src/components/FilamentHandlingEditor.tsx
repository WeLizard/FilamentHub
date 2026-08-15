import { ChevronDown, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type {
  FilamentChemicalGuidance,
  FilamentEnclosureRequirement,
} from '../types/api';
import { Dropdown } from './Dropdown';
import { ChemicalSafetyNotice } from './ChemicalSafetyNotice';

export interface FilamentHandlingFormValue {
  dryingRequired: boolean;
  dryingTemperatureC: number | '';
  dryingDurationHours: number | '';
  enclosureRequirement: FilamentEnclosureRequirement;
  chamberTemperatureC: number | '';
  bedAdhesivesText: string;
  chemicals: FilamentChemicalGuidance[];
}

interface FilamentHandlingEditorProps {
  value: FilamentHandlingFormValue;
  onChange: (value: FilamentHandlingFormValue) => void;
  disabled?: boolean;
  compact?: boolean;
}

export function parseBedAdhesives(value: string): string[] {
  const seen = new Set<string>();
  return value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter((item) => {
      const key = item.toLocaleLowerCase();
      if (!item || seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 12);
}

export function normalizeChemicalGuidance(
  chemicals: FilamentChemicalGuidance[],
): FilamentChemicalGuidance[] {
  return chemicals
    .filter((item) => item.name.trim())
    .map((item) => ({
      name: item.name.trim(),
      purpose: item.purpose?.trim() || null,
      safety_note: item.safety_note?.trim() || null,
      hazardous: item.hazardous,
    }))
    .slice(0, 12);
}

export function isHandlingGuidanceComplete(value: FilamentHandlingFormValue): boolean {
  if (value.dryingRequired && (
    value.dryingTemperatureC === '' || value.dryingDurationHours === ''
  )) {
    return false;
  }
  return value.enclosureRequirement !== 'active' || value.chamberTemperatureC !== '';
}

export function FilamentHandlingEditor({
  value,
  onChange,
  disabled = false,
  compact = false,
}: FilamentHandlingEditorProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const inputClass = 'h-10 w-full rounded-lg border border-white/20 bg-white/10 px-3 py-2 text-sm text-white placeholder-gray-500 outline-none transition focus:ring-2 focus:ring-purple-500 disabled:cursor-not-allowed disabled:opacity-60';

  const updateChemical = (index: number, patch: Partial<FilamentChemicalGuidance>) => {
    const chemicals = value.chemicals.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...patch } : item
    ));
    onChange({ ...value, chemicals });
  };

  return (
    <section className={`rounded-xl border border-white/10 bg-black/10 ${compact ? 'p-3' : 'p-4'}`}>
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
        className="flex w-full items-start justify-between gap-4 text-left"
      >
        <span>
          <span className="block font-semibold text-white">{t('filamentHandling.title')}</span>
          <span className="mt-1 block text-xs leading-5 text-gray-400">{t('filamentHandling.editorHint')}</span>
          {disabled && (
            <span className="mt-1 block text-xs leading-5 text-amber-200/80">{t('filamentHandling.lockedHint')}</span>
          )}
        </span>
        <ChevronDown
          className={`mt-1 h-5 w-5 shrink-0 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
        />
      </button>

      {expanded && <div className="mt-4">
        <div className="grid items-start gap-3 md:grid-cols-2">
          <div>
            <span className="mb-1.5 block text-sm font-medium text-gray-300">
              {t('filamentHandling.dryingSection')}
            </span>
            <label className="flex h-[50px] cursor-pointer items-center justify-between gap-3 rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-sm text-gray-200">
              <span>{t('filamentHandling.dryingQuestion')}</span>
              <input
                type="checkbox"
                checked={value.dryingRequired}
                disabled={disabled}
                onChange={(event) => onChange({
                  ...value,
                  dryingRequired: event.target.checked,
                  dryingTemperatureC: event.target.checked ? value.dryingTemperatureC : '',
                  dryingDurationHours: event.target.checked ? value.dryingDurationHours : '',
                })}
                className="h-4 w-4 rounded border-white/30 bg-white/10 text-purple-500 focus:ring-purple-500"
              />
            </label>
            {value.dryingRequired && (
              <div className="mt-3 grid grid-cols-2 gap-3">
                <label>
                  <span className="mb-1.5 block text-xs font-medium text-gray-400">
                    {t('filamentHandling.dryingTemperature')}
                  </span>
                  <input
                    type="number"
                    value={value.dryingTemperatureC}
                    disabled={disabled}
                    min={0}
                    max={200}
                    step={1}
                    onChange={(event) => onChange({
                      ...value,
                      dryingTemperatureC: event.target.value === '' ? '' : Number(event.target.value),
                    })}
                    className={inputClass}
                  />
                </label>
                <label>
                  <span className="mb-1.5 block text-xs font-medium text-gray-400">
                    {t('filamentHandling.dryingDuration')}
                  </span>
                  <input
                    type="number"
                    value={value.dryingDurationHours}
                    disabled={disabled}
                    min={0.25}
                    max={336}
                    step={0.25}
                    onChange={(event) => onChange({
                      ...value,
                      dryingDurationHours: event.target.value === '' ? '' : Number(event.target.value),
                    })}
                    className={inputClass}
                  />
                </label>
              </div>
            )}
          </div>
          <div>
            <span className="mb-1.5 block text-sm font-medium text-gray-300">
              {t('filamentHandling.enclosureQuestion')}
            </span>
            <div className={value.enclosureRequirement === 'active' ? 'grid grid-cols-2 gap-3' : ''}>
              <Dropdown
                value={value.enclosureRequirement}
                disabled={disabled}
                onChange={(next) => {
                  const enclosureRequirement = String(next) as FilamentEnclosureRequirement;
                  onChange({
                    ...value,
                    enclosureRequirement,
                    chamberTemperatureC: enclosureRequirement === 'active'
                      ? value.chamberTemperatureC
                      : '',
                  });
                }}
                options={(['none', 'passive', 'active'] as const).map((option) => ({
                  value: option,
                  label: t(`filamentHandling.enclosureOptions.${option}`),
                }))}
              />
              {value.enclosureRequirement === 'active' && (
                <label className="relative">
                  <span className="sr-only">{t('filamentHandling.chamberTemperature')}</span>
                  <input
                    type="number"
                    value={value.chamberTemperatureC}
                  disabled={disabled}
                  min={0}
                  max={150}
                    step={1}
                    placeholder={t('filamentHandling.chamberTemperatureShort')}
                  onChange={(event) => onChange({
                    ...value,
                    chamberTemperatureC: event.target.value === '' ? '' : Number(event.target.value),
                  })}
                    className="h-[50px] w-full rounded-xl border border-white/20 bg-white/10 px-4 py-3 pr-10 text-white placeholder-gray-500 outline-none transition focus:ring-2 focus:ring-purple-500 disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500">°C</span>
                </label>
              )}
            </div>
          </div>
        </div>

        <label className="mt-4 block">
          <span className="mb-1.5 block text-sm font-medium text-gray-300">
            {t('filamentHandling.bedAdhesives')}
          </span>
          <textarea
            value={value.bedAdhesivesText}
            disabled={disabled}
            rows={2}
            maxLength={1200}
            onChange={(event) => onChange({ ...value, bedAdhesivesText: event.target.value })}
            placeholder={t('filamentHandling.bedAdhesivesPlaceholder')}
            className={`${inputClass} h-auto min-h-16 resize-y`}
          />
          <span className="mt-1 block text-xs text-gray-500">{t('filamentHandling.listHint')}</span>
        </label>

        <div className="mt-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-gray-200">{t('filamentHandling.chemicals')}</h4>
            <p className="mt-1 text-xs text-gray-500">{t('filamentHandling.chemicalsHint')}</p>
          </div>
          <button
            type="button"
            disabled={disabled || value.chemicals.length >= 12}
            onClick={() => onChange({
              ...value,
              chemicals: [
                ...value.chemicals,
                { name: '', purpose: '', safety_note: '', hazardous: false },
              ],
            })}
            className="inline-flex items-center gap-2 rounded-lg border border-purple-400/30 bg-purple-500/15 px-3 py-2 text-sm text-purple-100 transition hover:bg-purple-500/25 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="h-4 w-4" />
            {t('filamentHandling.addChemical')}
          </button>
        </div>

        {value.chemicals.length > 0 && (
          <div className="mt-3 space-y-3">
            {value.chemicals.map((chemical, index) => (
              <div key={index} className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                <div className="grid gap-3 md:grid-cols-2">
                  <input
                    value={chemical.name}
                    disabled={disabled}
                    maxLength={100}
                    onChange={(event) => updateChemical(index, { name: event.target.value })}
                    placeholder={t('filamentHandling.chemicalName')}
                    className={inputClass}
                  />
                  <input
                    value={chemical.purpose ?? ''}
                    disabled={disabled}
                    maxLength={200}
                    onChange={(event) => updateChemical(index, { purpose: event.target.value })}
                    placeholder={t('filamentHandling.chemicalPurpose')}
                    className={inputClass}
                  />
                </div>
                <textarea
                  value={chemical.safety_note ?? ''}
                  disabled={disabled}
                  required={chemical.hazardous}
                  aria-invalid={chemical.hazardous && !chemical.safety_note?.trim()}
                  rows={2}
                  maxLength={500}
                  onChange={(event) => updateChemical(index, { safety_note: event.target.value })}
                  placeholder={t(chemical.hazardous
                    ? 'filamentHandling.safetyNoteRequired'
                    : 'filamentHandling.safetyNote')}
                  className={`mt-3 ${inputClass} resize-y ${chemical.hazardous && !chemical.safety_note?.trim() ? 'border-rose-400/60' : ''}`}
                />
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                  <label className="inline-flex items-center gap-2 text-xs text-amber-200">
                    <input
                      type="checkbox"
                      checked={chemical.hazardous}
                      disabled={disabled}
                      onChange={(event) => updateChemical(index, { hazardous: event.target.checked })}
                      className="h-4 w-4 rounded border-white/30 bg-white/10 text-amber-500 focus:ring-amber-500"
                    />
                    {t('filamentHandling.hazardous')}
                  </label>
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => onChange({
                      ...value,
                      chemicals: value.chemicals.filter((_, itemIndex) => itemIndex !== index),
                    })}
                    className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs text-rose-300 transition hover:bg-rose-500/10 hover:text-rose-200"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    {t('filamentHandling.removeChemical')}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <ChemicalSafetyNotice />
        </div>
      </div>}
    </section>
  );
}
