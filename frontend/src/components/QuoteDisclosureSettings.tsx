import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Dropdown } from './Dropdown';
import { InputWithSuffix } from './InputWithSuffix';

export type QuoteTaxKind = 'tax' | 'vat';
export type QuoteTaxMode = 'hide' | 'included' | 'separate';

interface QuoteDisclosureSettingsProps {
  /** "By work" cost breakdown instead of a single total. */
  byWork: boolean;
  onByWorkChange: (value: boolean) => void;
  byWorkAvailable?: boolean;
  note: string;
  onNoteChange: (value: string) => void;
  taxKind: QuoteTaxKind;
  onTaxKindChange: (value: QuoteTaxKind) => void;
  taxMode: QuoteTaxMode;
  onTaxModeChange: (value: QuoteTaxMode) => void;
  taxAvailable?: boolean;
  taxSeparateAvailable?: boolean;
  delivery: number;
  onDeliveryChange: (value: number) => void;
  currencySymbol: string;
  children?: ReactNode;
}

const textareaClass =
  'w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-2.5 text-sm text-white placeholder:text-slate-500 transition-all focus:border-transparent focus:outline-none focus:ring-2 focus:ring-cyan-400/60';

const Row: React.FC<{ label: string; children: ReactNode }> = ({ label, children }) => (
  <div>
    <p className="mb-1.5 text-sm font-medium text-slate-300">{label}</p>
    {children}
  </div>
);

/** What the customer sees in the quote; shared by the profile defaults, the quote dialog and the draft editor. */
export const QuoteDisclosureSettings: React.FC<QuoteDisclosureSettingsProps> = ({
  byWork, onByWorkChange, byWorkAvailable = true, note, onNoteChange,
  taxKind, onTaxKindChange, taxMode, onTaxModeChange, taxAvailable = true, taxSeparateAvailable = true,
  delivery, onDeliveryChange, currencySymbol, children,
}) => {
  const { t } = useTranslation();
  const tc = (key: string) => t(`profilePage.calculator.${key}`);
  const choices = [
    { value: false, label: tc('quoteCostSingle'), disabled: false },
    { value: true, label: tc('quoteCostByWork'), disabled: !byWorkAvailable },
  ];
  const kindOptions = [
    { value: 'tax', label: tc('quoteTaxGeneric') },
    { value: 'vat', label: tc('quoteTaxVat') },
  ];
  const modeOptions = [
    { value: 'hide', label: tc('quoteTaxHide') },
    { value: 'included', label: tc('quoteTaxIncluded') },
    {
      value: 'separate',
      label: tc('quoteTaxSeparate'),
      disabled: !taxSeparateAvailable,
      title: taxSeparateAvailable ? undefined : tc('quoteTaxSplitUnrepresentable'),
    },
  ];
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-white">{tc('quoteDisclosureTitle')}</h3>
        <p className="mt-1 text-xs leading-5 text-slate-400">{tc('quoteInternalEconomicsHidden')}</p>
      </div>
      <Row label={tc('quoteCostSection')}>
        <div className="inline-flex rounded-xl border border-white/10 bg-black/15 p-1">
          {choices.map((choice) => (
            <button
              key={String(choice.value)}
              type="button"
              aria-pressed={byWork === choice.value}
              disabled={choice.disabled}
              title={choice.disabled ? tc('quoteCostByWorkUnavailable') : undefined}
              onClick={() => onByWorkChange(choice.value)}
              className={`rounded-lg px-3.5 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
                byWork === choice.value ? 'bg-cyan-500 text-slate-950 shadow' : 'text-slate-300 hover:bg-white/5 hover:text-white'
              }`}
            >
              {choice.label}
            </button>
          ))}
        </div>
        {!byWorkAvailable && <p className="mt-1.5 text-xs leading-5 text-amber-200">{tc('quoteCostByWorkUnavailable')}</p>}
      </Row>
      {byWork && byWorkAvailable && (
        <Row label={tc('quoteBreakdownNoteLabel')}>
          <textarea
            className={`${textareaClass} min-h-16 resize-y`}
            value={note}
            onChange={(event) => onNoteChange(event.target.value)}
            placeholder={tc('quoteBreakdownNotePlaceholder')}
            maxLength={500}
          />
        </Row>
      )}
      <Row label={tc('quoteTaxSection')}>
        <div className="flex flex-wrap items-center gap-2">
          <Dropdown
            className="w-52"
            size="sm"
            clearable={false}
            disabled={!taxAvailable}
            label={tc('quoteTaxDisplay')}
            labelClassName="sr-only"
            value={taxMode}
            options={modeOptions}
            onChange={(value) => onTaxModeChange(value as QuoteTaxMode)}
          />
          <Dropdown
            className="w-28"
            size="sm"
            clearable={false}
            disabled={!taxAvailable || taxMode === 'hide'}
            label={tc('quoteTaxKind')}
            labelClassName="sr-only"
            value={taxKind}
            options={kindOptions}
            onChange={(value) => onTaxKindChange(value as QuoteTaxKind)}
          />
        </div>
        {!taxAvailable && <p className="mt-1.5 text-xs leading-5 text-amber-200">{tc('quoteTaxUnavailable')}</p>}
        {taxAvailable && taxMode === 'separate' && !taxSeparateAvailable && (
          <p className="mt-1.5 text-xs leading-5 text-amber-200">{tc('quoteTaxSplitUnrepresentable')}</p>
        )}
      </Row>
      <Row label={tc('quoteCustomerDeliveryLabel')}>
        <InputWithSuffix value={delivery} onChange={(value) => onDeliveryChange(Math.max(0, value))} placeholder="0" suffix={currencySymbol} step="0.01" />
        <p className="mt-1.5 text-xs leading-5 text-slate-400">{tc('quoteCustomerDeliveryHint')}</p>
      </Row>
      {children}
    </div>
  );
};
