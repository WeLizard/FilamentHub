import { useTranslation } from 'react-i18next';

import type { CatalogCurationSourceFact, CatalogCurationUnmappedFact } from '../../../types/api';
import { externalUrl, externalUrlDisplay } from '../../../utils/externalUrl';

interface SourceFactsPanelsProps {
  filamentKeys: string[];
  facts: Array<{ item: CatalogCurationSourceFact; index: number }>;
  unmapped: Array<{ item: CatalogCurationUnmappedFact; index: number }>;
  disabled: boolean;
  readonly: boolean;
  onUpdateSourceFact: (index: number, changes: Partial<CatalogCurationSourceFact>) => void;
  onRemoveSourceFact: (index: number) => void;
  onAddSourceFact: () => void;
  onUpdateUnmappedFact: (index: number, changes: Partial<CatalogCurationUnmappedFact>) => void;
  onRemoveUnmappedFact: (index: number) => void;
  onAddUnmappedFact: () => void;
}

export function SourceFactsPanels({
  filamentKeys, facts: selectedFacts, unmapped: selectedUnmapped, disabled, readonly,
  onUpdateSourceFact, onRemoveSourceFact, onAddSourceFact,
  onUpdateUnmappedFact, onRemoveUnmappedFact, onAddUnmappedFact,
}: SourceFactsPanelsProps) {
  const { t } = useTranslation();
  return <>
          <details className="rounded-2xl border border-white/10 bg-slate-950/35 p-4">
  <summary className="cursor-pointer text-sm font-semibold text-white">
    {t('adminCatalogImport.curation.sourceFacts')} · {selectedFacts.length}
  </summary>
  <p className="mt-2 text-xs leading-5 text-gray-400">{t('adminCatalogImport.curation.sourceFactsHint')}</p>
  <fieldset disabled={disabled} className="mt-4 max-h-[56vh] space-y-3 overflow-y-auto disabled:opacity-70">
    {selectedFacts.map(({ item, index }) => {
      return <div key={index} className="space-y-3 rounded-xl border border-white/10 p-3">
        <div className="flex flex-wrap gap-3">
          <label className="text-xs text-gray-400">{t('adminCatalogImport.curation.filamentKey')}
            <select aria-label={`${t('adminCatalogImport.curation.filamentKey')} ${index + 1} fact`}
              value={item.filament_key}
              onChange={(event) => onUpdateSourceFact(index, { filament_key: event.target.value })}
              className="ml-2 max-w-64 rounded bg-gray-900 p-2 text-gray-200">
              {filamentKeys.map((key) => <option key={key} value={key}>{key}</option>)}
            </select>
          </label>
          <label className="text-xs text-gray-400">{t('adminCatalogImport.curation.propertyName')}
            <input aria-label={`${t('adminCatalogImport.curation.propertyName')} ${index + 1} fact`}
              value={item.property_name}
              onChange={(event) => onUpdateSourceFact(index, { property_name: event.target.value })}
              className="ml-2 max-w-full rounded bg-gray-900 p-2 text-gray-200" />
          </label>
          <label className="text-xs text-gray-400">{t('adminCatalogImport.curation.disposition')}
            <select aria-label={`${t('adminCatalogImport.curation.disposition')} ${index + 1}`}
              value={item.disposition}
              onChange={(event) => onUpdateSourceFact(index, {
                disposition: event.target.value as CatalogCurationSourceFact['disposition'],
                mapped_fields: event.target.value === 'mapped' ? item.mapped_fields : [],
              })}
              className="ml-2 rounded bg-gray-900 p-2 text-gray-200">
              {(['mapped', 'unsupported', 'unresolved'] as const).map((state) => <option key={state} value={state}>{t(`adminCatalogImport.curation.dispositionState.${state}`)}</option>)}
            </select>
          </label>
        </div>
        <label className="block text-xs text-gray-400">{t('adminCatalogImport.curation.valueSummary')}
          <textarea aria-label={`${t('adminCatalogImport.curation.valueSummary')} ${index + 1} fact`}
            value={item.value_summary} rows={2}
            onChange={(event) => onUpdateSourceFact(index, { value_summary: event.target.value })}
            className="mt-1 block w-full rounded bg-gray-900 p-2 text-gray-200" />
        </label>
        {item.disposition === 'mapped' && <label className="block text-xs text-gray-400">{t('adminCatalogImport.curation.mappedFields')}
          <textarea aria-label={`${t('adminCatalogImport.curation.mappedFields')} ${index + 1}`}
            value={item.mapped_fields.join('\n')} rows={2}
            onChange={(event) => onUpdateSourceFact(index, { mapped_fields: event.target.value.split('\n').map((field) => field.trim()).filter(Boolean) })}
            className="mt-1 block w-full rounded bg-gray-900 p-2 font-mono text-gray-200" />
        </label>}
        <label className="block text-xs text-gray-400">{t('adminCatalogImport.curation.sources')}
          <textarea aria-label={`${t('adminCatalogImport.curation.sources')} ${index + 1} fact`}
            value={item.source_urls.join('\n')} rows={2}
            onChange={(event) => onUpdateSourceFact(index, { source_urls: event.target.value.split('\n').map((url) => url.trim()).filter(Boolean) })}
            className="mt-1 block w-full rounded bg-gray-900 p-2 text-gray-200" />
        </label>
        {item.source_urls.map((url, sourceIndex) => {
          const safeUrl = externalUrl(url);
          return safeUrl ? <a key={sourceIndex} href={safeUrl} target="_blank" rel="noopener noreferrer" className="block break-all text-xs text-cyan-300 underline">{externalUrlDisplay(url)}</a> : null;
        })}
        {!readonly && <button type="button" onClick={() => onRemoveSourceFact(index)} className="text-xs text-red-300">{t('adminCatalogImport.curation.removeSourceFact')}</button>}
      </div>;
    })}
  </fieldset>
  <div className="mt-3 flex flex-wrap items-center gap-3">
    {!readonly && filamentKeys.length > 0 && <button type="button" onClick={onAddSourceFact} className="rounded-lg border border-white/15 px-3 py-2 text-xs font-semibold text-gray-200">
      {t('adminCatalogImport.curation.addSourceFact')}
    </button>}
  </div>
</details>

<details className="rounded-2xl border border-amber-400/20 bg-amber-500/5 p-4">
  <summary className="cursor-pointer text-sm font-semibold text-white">
    {t('adminCatalogImport.curation.unmappedFacts')} · {selectedUnmapped.length}
  </summary>
  <p className="mt-2 text-xs leading-5 text-gray-400">{t('adminCatalogImport.curation.unmappedFactsHint')}</p>
  <fieldset disabled={disabled} className="mt-4 space-y-3 disabled:opacity-70">
    {selectedUnmapped.map(({ item, index }) => (
      <div key={index} className="space-y-3 rounded-xl border border-amber-400/15 p-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-xs text-gray-300">{t('adminCatalogImport.curation.publicAction')}
            <select aria-label={`${t('adminCatalogImport.curation.publicAction')} ${index + 1}`}
              value={item.public_action ?? 'none'}
              onChange={(event) => onUpdateUnmappedFact(index, { public_action: event.target.value as CatalogCurationUnmappedFact['public_action'] })}
              className="mt-1 block max-w-full rounded bg-gray-900 p-2 text-sm text-white">
              <option value="none">{t('adminCatalogImport.curation.publicActions.none')}</option>
              <option value="publish">{t('adminCatalogImport.curation.publicActions.publish')}</option>
              <option value="remove">{t('adminCatalogImport.curation.publicActions.remove')}</option>
            </select>
          </label>
          <label className="block text-xs text-gray-300">{t('adminCatalogImport.curation.evidenceKind')}
            <select aria-label={`${t('adminCatalogImport.curation.evidenceKind')} ${index + 1} unmapped`}
              value={item.kind ?? ''}
              onChange={(event) => onUpdateUnmappedFact(index, { kind: event.target.value ? event.target.value as 'direct' | 'inferred' : null })}
              className="mt-1 block max-w-full rounded bg-gray-900 p-2 text-sm text-white">
              <option value="">{t('adminCatalogImport.curation.chooseEvidenceKind')}</option>
              <option value="direct">{t('adminCatalogImport.curation.kind.direct')}</option>
              <option value="inferred">{t('adminCatalogImport.curation.kind.inferred')}</option>
            </select>
          </label>
        </div>
        {item.public_action === 'publish' && item.kind == null && (
          <p role="status" className="text-xs text-amber-200">{t('adminCatalogImport.curation.publicFactNeedsKind')}</p>
        )}
        {item.public_action === 'publish' && item.kind === 'inferred' && !item.explanation?.trim() && (
          <p role="status" className="text-xs text-amber-200">{t('adminCatalogImport.curation.publicFactNeedsExplanation')}</p>
        )}
        <div className="flex flex-wrap gap-3">
          <label className="text-xs text-gray-400">{t('adminCatalogImport.curation.filamentKey')}
            <select aria-label={`${t('adminCatalogImport.curation.filamentKey')} ${index + 1}`}
              value={item.filament_key}
              onChange={(event) => onUpdateUnmappedFact(index, { filament_key: event.target.value })}
              className="ml-2 max-w-64 rounded bg-gray-900 p-2 text-gray-200">
              {filamentKeys.map((key) => <option key={key} value={key}>{key}</option>)}
            </select>
          </label>
          <label className="text-xs text-gray-400">{t('adminCatalogImport.curation.propertyName')}
            <input aria-label={`${t('adminCatalogImport.curation.propertyName')} ${index + 1}`}
              value={item.property_name}
              onChange={(event) => onUpdateUnmappedFact(index, { property_name: event.target.value })}
              className="ml-2 max-w-full rounded bg-gray-900 p-2 text-gray-200" />
          </label>
        </div>
        <label className="block text-xs text-gray-400">{t('adminCatalogImport.curation.valueSummary')}
          <textarea aria-label={`${t('adminCatalogImport.curation.valueSummary')} ${index + 1}`}
            value={item.value_summary} rows={2}
            onChange={(event) => onUpdateUnmappedFact(index, { value_summary: event.target.value })}
            className="mt-1 block w-full rounded bg-gray-900 p-2 text-gray-200" />
        </label>
        <label className="block text-xs text-gray-400">{t('adminCatalogImport.curation.sources')}
          <textarea aria-label={`${t('adminCatalogImport.curation.sources')} ${index + 1} unmapped`}
            value={item.source_urls.join('\n')} rows={2}
            onChange={(event) => onUpdateUnmappedFact(index, { source_urls: event.target.value.split('\n').map((url) => url.trim()).filter(Boolean) })}
            className="mt-1 block w-full rounded bg-gray-900 p-2 text-gray-200" />
        </label>
        {item.source_urls.map((url, sourceIndex) => {
          const safeUrl = externalUrl(url);
          return safeUrl ? <a key={sourceIndex} href={safeUrl} target="_blank" rel="noopener noreferrer" className="block break-all text-xs text-cyan-300 underline">{externalUrlDisplay(url)}</a> : null;
        })}
        <label className="block text-xs text-gray-400">{item.kind === 'inferred'
          ? t('adminCatalogImport.curation.inferenceExplanation')
          : t('adminCatalogImport.curation.explanation')}
          <textarea aria-label={`${t(item.kind === 'inferred'
            ? 'adminCatalogImport.curation.inferenceExplanation'
            : 'adminCatalogImport.curation.explanation')} ${index + 1} unmapped`}
            value={item.explanation ?? ''} rows={2}
            onChange={(event) => onUpdateUnmappedFact(index, { explanation: event.target.value })}
            className="mt-1 block w-full rounded bg-gray-900 p-2 text-gray-200" />
        </label>
        {!readonly && <button type="button" onClick={() => onRemoveUnmappedFact(index)} className="text-xs text-red-300">{t('adminCatalogImport.curation.removeUnmappedFact')}</button>}
      </div>
    ))}
    {!readonly && filamentKeys.length > 0 && <button type="button" onClick={onAddUnmappedFact} className="rounded-lg border border-amber-400/30 px-3 py-2 text-xs font-semibold text-amber-200">
      {t('adminCatalogImport.curation.addUnmappedFact')}
    </button>}
  </fieldset>
</details>
  </>;
}
