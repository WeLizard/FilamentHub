import React from 'react';
import type { OrcaPresetSchema } from '../utils/orcaPresetSchema';
import { orcaExtraFieldKind } from '../utils/orcaPresetSettings';
import { schemaOptionText, type ViewLanguage } from '../utils/orcaSchemaView';
import { InfoHint } from './InfoHint';

interface OrcaSchemaFieldProps {
  schema: OrcaPresetSchema;
  lang: ViewLanguage;
  fieldKey: string;
  value: string;
  placeholder?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}

const INPUT_CLASS = 'w-full pl-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all';

export const OrcaSchemaField: React.FC<OrcaSchemaFieldProps> = ({
  schema, lang, fieldKey, value, placeholder, disabled = false, onChange,
}) => {
  const option = schema.options[fieldKey];
  if (!option) return null;

  const { label, tooltip, unit } = schemaOptionText(schema, fieldKey, lang);
  const kind = orcaExtraFieldKind(option);
  const id = `orca-field-${fieldKey}`;
  const suffix = kind === 'percent' ? '%' : unit;

  return (
    <div>
      <label htmlFor={id} className="block text-gray-300 mb-1 text-sm">
        {label}
        {tooltip && <> <InfoHint text={tooltip} /></>}
      </label>
      <div className="relative">
        <input
          id={id}
          type={kind === 'text' ? 'text' : 'number'}
          value={kind === 'percent' ? value.replace(/%$/, '') : value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          {...(kind === 'text' ? {} : {
            min: option.min,
            max: option.max,
            step: option.type === 'int' ? 1 : 'any',
          })}
          className={`${INPUT_CLASS} ${suffix ? 'pr-16' : 'pr-3'} disabled:cursor-not-allowed disabled:opacity-60`}
        />
        {suffix && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">
            {suffix}
          </span>
        )}
      </div>
    </div>
  );
};
