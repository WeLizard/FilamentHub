import { useMemo, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  ADDITIVE_CODES,
  DECORATIVE_VISUAL_EFFECT_CODES,
  PROPERTY_CLAIM_CODES,
  deriveVisualEffectsFromAdditives,
} from '../data/filamentFeatures';
import type { FilamentAdditive, FilamentPropertyClaim } from '../types/api';
import { Dropdown } from './Dropdown';

interface FilamentFeaturesEditorProps {
  effects: string[];
  onEffectsChange: (effects: string[]) => void;
  additives: FilamentAdditive[];
  onAdditivesChange: (additives: FilamentAdditive[]) => void;
  propertyClaims: FilamentPropertyClaim[];
  onPropertyClaimsChange: (claims: FilamentPropertyClaim[]) => void;
  allowCustom?: boolean;
  compact?: boolean;
}

const normalizeCustomCode = (value: string) => value.trim().toLowerCase().replace(/\s+/g, '_');
const ADDITIVE_CODE_SET = new Set<string>(ADDITIVE_CODES);
const PROPERTY_CLAIM_CODE_SET = new Set<string>(PROPERTY_CLAIM_CODES);

export const FilamentFeaturesEditor: React.FC<FilamentFeaturesEditorProps> = ({
  effects,
  onEffectsChange,
  additives,
  onAdditivesChange,
  propertyClaims,
  onPropertyClaimsChange,
  allowCustom = false,
  compact = false,
}) => {
  const { t } = useTranslation();
  const [customAdditive, setCustomAdditive] = useState('');
  const [customClaim, setCustomClaim] = useState('');
  const derivedEffects = useMemo(() => deriveVisualEffectsFromAdditives(additives), [additives]);

  const compositionOptions = useMemo(() => {
    const selectedCodes = additives.map(item => item.code);
    const additiveCodes = [...ADDITIVE_CODES, ...selectedCodes.filter(code => !ADDITIVE_CODE_SET.has(code))];
    const effectCodes = [...DECORATIVE_VISUAL_EFFECT_CODES, ...effects];

    return [
      ...[...new Set(additiveCodes)].map(code => ({
        value: `additive:${code}`,
        label: t(`filamentFeatures.additives.${code}`, { defaultValue: code.replaceAll('_', ' ') }),
        group: t('filamentFeatures.physicalComposition'),
      })),
      ...[...new Set(effectCodes)].map(code => ({
        value: `effect:${code}`,
        label: t(`filamentFeatures.effects.${code}`, { defaultValue: code.replaceAll('_', ' ') }),
        group: t('filamentFeatures.visualEffects'),
      })),
    ];
  }, [additives, effects, t]);

  const claimOptions = useMemo(() => {
    const selectedCodes = propertyClaims.map(item => item.code);
    const codes = [...PROPERTY_CLAIM_CODES, ...selectedCodes.filter(code => !PROPERTY_CLAIM_CODE_SET.has(code))];
    return [...new Set(codes)].map(code => ({
      value: code,
      label: t(`filamentFeatures.claims.${code}`, { defaultValue: code.replaceAll('_', ' ') }),
    }));
  }, [propertyClaims, t]);

  const setSelectedAdditives = (codes: (string | number)[]) => {
    const nextCodes = codes.map(String);
    onAdditivesChange(nextCodes.map(code => additives.find(item => item.code === code) ?? { code }));
  };

  const setSelectedComposition = (values: (string | number)[]) => {
    const selected = values.map(String);
    const additiveCodes = selected
      .filter(value => value.startsWith('additive:'))
      .map(value => value.slice('additive:'.length));
    const effectCodes = selected
      .filter(value => value.startsWith('effect:'))
      .map(value => value.slice('effect:'.length));

    setSelectedAdditives(additiveCodes);
    onEffectsChange(effectCodes);
  };

  const setSelectedClaims = (codes: (string | number)[]) => {
    const nextCodes = codes.map(String);
    onPropertyClaimsChange(nextCodes.map(code => propertyClaims.find(item => item.code === code) ?? { code }));
  };

  const addCustom = (
    value: string,
    current: string[],
    onChange: (next: string[]) => void,
    clear: () => void,
  ) => {
    const code = normalizeCustomCode(value);
    if (code && !current.includes(code)) onChange([...current, code]);
    clear();
  };

  const customInput = (
    value: string,
    setValue: (value: string) => void,
    onAdd: () => void,
  ) => allowCustom ? (
    <div className={`mt-2 flex gap-2 ${compact ? 'text-sm' : ''}`}>
      <input
        type="text"
        value={value}
        onChange={event => setValue(event.target.value)}
        onKeyDown={event => {
          if (event.key === 'Enter') {
            event.preventDefault();
            onAdd();
          }
        }}
        maxLength={40}
        placeholder={t('filamentFeatures.customPlaceholder')}
        className={`min-w-0 flex-1 px-3 bg-white/10 border border-white/20 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 ${compact ? 'py-1.5' : 'py-2'}`}
      />
      <button
        type="button"
        onClick={onAdd}
        disabled={!value.trim()}
        className={`px-3 rounded-lg border border-purple-400/40 bg-purple-500/15 text-purple-100 hover:bg-purple-500/25 disabled:opacity-40 transition-colors ${compact ? 'py-1.5' : 'py-2'}`}
        title={t('filamentFeatures.addCustom')}
      >
        <Plus className="w-4 h-4" />
      </button>
    </div>
  ) : null;

  return (
    <div className={compact ? 'grid grid-cols-1 items-start gap-2.5 lg:grid-cols-2' : 'space-y-5'}>
      <div className={compact ? 'rounded-xl border border-white/10 bg-black/10 p-2.5' : ''}>
        <label className="block text-gray-300 mb-1 text-sm font-medium">{t('filamentFeatures.composition')}</label>
        <p className="text-xs text-gray-500 mb-2">{t('filamentFeatures.compositionHint')}</p>
        <Dropdown
          value=""
          onChange={() => undefined}
          multiple
          selectedValues={[
            ...additives.map(item => `additive:${item.code}`),
            ...effects.map(effect => `effect:${effect}`),
          ]}
          onMultiChange={setSelectedComposition}
          options={compositionOptions}
          placeholder={t('filamentFeatures.selectAdditives')}
          size={compact ? 'sm' : 'md'}
        />
        {customInput(customAdditive, setCustomAdditive, () => addCustom(
          customAdditive,
          additives.map(item => item.code),
          codes => setSelectedAdditives(codes),
          () => setCustomAdditive(''),
        ))}
        {additives.length > 0 && (
          <div className="mt-2 space-y-2">
            {additives.map((item, index) => (
              <div
                key={item.code}
                className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-center gap-2 rounded-lg border border-white/10 bg-black/15 px-2.5 py-1.5"
              >
                <span className="col-span-2 col-start-1 row-start-1 min-w-0 break-words text-sm leading-snug text-gray-200">
                  {t(`filamentFeatures.additives.${item.code}`, { defaultValue: item.code.replaceAll('_', ' ') })}
                </span>
                <button
                  type="button"
                  onClick={() => onAdditivesChange(additives.filter((_, itemIndex) => itemIndex !== index))}
                  className="col-start-3 row-start-1 justify-self-end p-1.5 text-gray-500 hover:text-red-300 transition-colors"
                  title={t('filamentFeatures.remove')}
                >
                  <X className="w-4 h-4" />
                </button>
                <div className="col-span-3 row-start-2 grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(7rem,auto)] gap-2">
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step="any"
                    value={item.content_percent ?? ''}
                    onChange={event => {
                      const next = [...additives];
                      next[index] = { ...item, content_percent: event.target.value === '' ? null : Number(event.target.value) };
                      onAdditivesChange(next);
                    }}
                    placeholder={t('filamentFeatures.percent')}
                    className="min-w-0 w-full px-2 py-1.5 bg-white/10 border border-white/15 rounded-md text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
                  />
                  <select
                    value={item.content_basis ?? ''}
                    onChange={event => {
                      const next = [...additives];
                      next[index] = { ...item, content_basis: (event.target.value || null) as FilamentAdditive['content_basis'] };
                      onAdditivesChange(next);
                    }}
                    className="min-w-0 w-full px-2 py-1.5 bg-gray-800 border border-white/15 rounded-md text-sm text-white focus:outline-none focus:ring-1 focus:ring-purple-500"
                    aria-label={t('filamentFeatures.contentBasis')}
                  >
                    <option value="">{t('filamentFeatures.basisUnknown')}</option>
                    <option value="weight">{t('filamentFeatures.weightBasis')}</option>
                    <option value="volume">{t('filamentFeatures.volumeBasis')}</option>
                  </select>
                </div>
              </div>
            ))}
          </div>
        )}
        {derivedEffects.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-gray-500">
            <span>{t('filamentFeatures.automaticPreview')}:</span>
            {derivedEffects.map(effect => (
              <span
                key={effect}
                className="rounded-full border border-cyan-300/15 bg-cyan-400/[0.07] px-2 py-0.5 text-cyan-100/80"
              >
                {t(`filamentFeatures.effects.${effect}`, { defaultValue: effect.replaceAll('_', ' ') })}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className={compact ? 'rounded-xl border border-white/10 bg-black/10 p-2.5' : ''}>
        <label className="block text-gray-300 mb-1 text-sm font-medium">{t('filamentFeatures.functionalProperties')}</label>
        <p className="text-xs text-gray-500 mb-2">{t('filamentFeatures.functionalPropertiesHint')}</p>
        <Dropdown
          value=""
          onChange={() => undefined}
          multiple
          selectedValues={propertyClaims.map(item => item.code)}
          onMultiChange={setSelectedClaims}
          options={claimOptions}
          placeholder={t('filamentFeatures.selectProperties')}
          size={compact ? 'sm' : 'md'}
        />
        {customInput(customClaim, setCustomClaim, () => addCustom(
          customClaim,
          propertyClaims.map(item => item.code),
          codes => setSelectedClaims(codes),
          () => setCustomClaim(''),
        ))}
        {propertyClaims.length > 0 && (
          <div className="mt-2 space-y-2">
            {propertyClaims.map((claim, index) => (
              <div key={claim.code} className="relative rounded-lg border border-white/10 bg-black/15">
                <details className="group px-3 py-2 pr-11">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm text-gray-200">
                    <span>{t(`filamentFeatures.claims.${claim.code}`, { defaultValue: claim.code.replaceAll('_', ' ') })}</span>
                    <span className="text-xs text-gray-500">
                      {claim.rating || claim.standard || t('filamentFeatures.addDetails')}
                    </span>
                  </summary>
                  <div className="grid grid-cols-1 gap-2 pt-3">
                    {(['value', 'standard', 'rating'] as const).map(field => (
                      <input
                        key={field}
                        type="text"
                        value={claim[field] ?? ''}
                        onChange={event => {
                          const next = [...propertyClaims];
                          next[index] = { ...claim, [field]: event.target.value || null };
                          onPropertyClaimsChange(next);
                        }}
                        maxLength={field === 'rating' ? 80 : 100}
                        placeholder={t(`filamentFeatures.${field}`)}
                        className="w-full px-2 py-1.5 bg-white/10 border border-white/15 rounded-md text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
                      />
                    ))}
                  </div>
                </details>
                <button
                  type="button"
                  onClick={() => onPropertyClaimsChange(propertyClaims.filter((_, itemIndex) => itemIndex !== index))}
                  className="absolute right-2 top-2 p-1 text-gray-500 hover:text-red-300 transition-colors"
                  title={t('filamentFeatures.remove')}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
