/** Read-only view of an Orca preset built from the generated Orca preset schema. */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, ChevronDown, ChevronRight, XCircle } from 'lucide-react';
import type { SettingMode } from '../data/orcaFieldModes';
import {
  loadFilamentPresetSchema,
  type OrcaPresetSchema,
} from '../utils/orcaPresetSchema';
import {
  buildSchemaView,
  OTHER_PAGE_ID,
  type CellValue,
  type FieldView,
  type GroupView,
  type RowView,
  type ViewLanguage,
} from '../utils/orcaSchemaView';
import { normalizeSiteLocale } from '../utils/siteLocale';
import { SettingModeSelector } from './SettingModeSelector';

const EMPTY_SCHEMA: OrcaPresetSchema = { kind: 'filament', pages: [], options: {} };

const GRID_CLASS = 'grid grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] gap-x-3 gap-y-1';

const CollapsibleBlock: React.FC<{ text: string }> = ({ text }) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const lines = text.split('\n');
  const Chevron = open ? ChevronDown : ChevronRight;

  return (
    <div className="min-w-0">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-1 max-w-full text-left text-gray-300 hover:text-white transition-colors"
      >
        <Chevron className="w-4 h-4 flex-shrink-0" />
        <span className="truncate font-mono text-xs">{lines[0] || '…'}</span>
        <span className="flex-shrink-0 text-xs text-gray-500">{t('orcaSchemaView.lines', { count: lines.length })}</span>
      </button>
      {open && (
        <pre className="mt-1 bg-white/5 p-2 rounded-lg text-xs text-gray-300 font-mono whitespace-pre-wrap break-words max-h-64 overflow-auto custom-scrollbar">
          {text}
        </pre>
      )}
    </div>
  );
};

const Cell: React.FC<{ cell: CellValue }> = ({ cell }) => {
  const { t } = useTranslation();
  switch (cell.kind) {
    case 'nil':
      return <span className="text-gray-400">{t('orcaSchemaView.inherited')}</span>;
    case 'empty':
      return <span className="text-gray-500">—</span>;
    case 'unsupported':
      return <span className="text-gray-500 italic text-xs">{t('orcaSchemaView.plateUnsupported')}</span>;
    case 'bool':
      return cell.value ? (
        <span className="inline-flex items-center gap-1 text-green-400">
          <CheckCircle2 className="w-4 h-4" />
          {t('viewPreset.yes')}
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 text-red-400">
          <XCircle className="w-4 h-4" />
          {t('viewPreset.no')}
        </span>
      );
    case 'color':
      return (
        <span className="inline-flex items-center gap-2">
          <span className="w-4 h-4 rounded border border-white/20" style={{ backgroundColor: cell.text }} />
          {cell.text}
        </span>
      );
    case 'block':
      return <CollapsibleBlock text={cell.text} />;
    default:
      return (
        <span className="min-w-0">
          {cell.text}
          {cell.unit && <span className="text-gray-400 ml-1 text-xs">{cell.unit}</span>}
        </span>
      );
  }
};

const Cells: React.FC<{ cells: CellValue[]; breakWords?: boolean }> = ({ cells, breakWords = true }) => (
  <div className={`flex flex-wrap items-baseline gap-x-2 gap-y-0.5 min-w-0 ${breakWords ? '[overflow-wrap:anywhere]' : ''}`}>
    {cells.map((cell, index) => (
      <Cell key={index} cell={cell} />
    ))}
  </div>
);

const hasBlock = (field: FieldView) => field.cells.some((cell) => cell.kind === 'block');

const Field: React.FC<{ field: FieldView; showKey?: boolean }> = ({ field, showKey }) => (
  <div className={`flex flex-col py-1 min-w-0 ${hasBlock(field) ? 'col-span-full' : ''}`} title={field.tooltip}>
    <span className="text-gray-400 text-xs mb-0.5 [overflow-wrap:anywhere]">{field.label}</span>
    {showKey && <span className="font-mono text-[10px] text-gray-500 mb-0.5 [overflow-wrap:anywhere]">{field.key}</span>}
    <div className="text-white font-medium text-sm">
      <Cells cells={field.cells} />
    </div>
  </div>
);

const Row: React.FC<{ row: RowView; showKeys: boolean }> = ({ row, showKeys }) => {
  switch (row.type) {
    case 'field':
      return <Field field={row.field} showKey={showKeys} />;
    case 'line':
      return (
        <div className="col-span-full flex flex-col py-1 min-w-0" title={row.tooltip}>
          <span className="text-gray-400 text-xs mb-0.5 break-words">{row.label}</span>
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-white font-medium text-sm">
            {row.fields.map((field) => (
              <div key={field.key} className="flex items-baseline gap-1.5 min-w-0" title={field.tooltip}>
                <span className="text-gray-400 text-xs font-normal">{field.label}</span>
                <Cells cells={field.cells} />
              </div>
            ))}
          </div>
        </div>
      );
    default:
      return (
        <div className="col-span-full overflow-x-auto">
          <table className="w-full max-w-lg text-sm">
            <thead>
              <tr>
                <th />
                {row.columns.map((column) => (
                  <th key={column} className="text-gray-400 text-xs font-normal text-left pb-1 pr-3">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {row.rows.map((tableRow) => (
                <tr key={tableRow.cells.find(Boolean)?.key ?? tableRow.label} title={tableRow.tooltip} className="border-t border-white/5">
                  <th scope="row" className="text-gray-300 text-xs font-normal text-left py-1 pr-3 align-top">
                    {tableRow.label}
                  </th>
                  {tableRow.cells.map((cell, index) => (
                    <td key={index} className="text-white font-medium py-1 pr-3 align-top">
                      {cell ? <Cells cells={cell.cells} breakWords={false} /> : <span className="text-gray-500">—</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
  }
};

const Group: React.FC<{ group: GroupView; showKeys: boolean }> = ({ group, showKeys }) => (
  <div>
    {group.title && (
      <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{group.title}</h4>
    )}
    <div className={GRID_CLASS}>
      {group.rows.map((row, index) => (
        <Row key={index} row={row} showKeys={showKeys} />
      ))}
    </div>
  </div>
);

interface OrcaSchemaSettingsViewProps {
  settings: Record<string, unknown>;
  mode: SettingMode;
  onModeChange: (mode: SettingMode) => void;
  title: string;
  /** Overrides the lazily loaded filament schema. */
  schema?: OrcaPresetSchema;
}

export const OrcaSchemaSettingsView: React.FC<OrcaSchemaSettingsViewProps> = ({
  settings,
  mode,
  onModeChange,
  title,
  schema: schemaOverride,
}) => {
  const { t, i18n } = useTranslation();
  const lang: ViewLanguage = normalizeSiteLocale(i18n.language) ?? 'en';
  const [loadedSchema, setLoadedSchema] = useState<OrcaPresetSchema | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    if (schemaOverride) return undefined;
    let cancelled = false;
    loadFilamentPresetSchema()
      .then((loaded) => {
        if (!cancelled) setLoadedSchema(loaded);
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [schemaOverride]);

  // Without the schema every key still shows up, under "Other parameters".
  const schema = schemaOverride ?? loadedSchema ?? (loadFailed ? EMPTY_SCHEMA : null);
  const view = useMemo(
    () => (schema ? buildSchemaView(schema, settings, mode, lang) : null),
    [schema, settings, mode, lang],
  );

  const tabs = useMemo(() => {
    if (!view) return [];
    const pageTabs = view.pages.map((page) => ({ id: page.id, title: page.title, groups: page.groups }));
    if (view.other.length === 0) return pageTabs;
    const otherGroup: GroupView = {
      title: '',
      rows: view.other.map((field) => ({ type: 'field', field })),
    };
    return [...pageTabs, { id: OTHER_PAGE_ID, title: t('orcaSchemaView.otherParams'), groups: [otherGroup] }];
  }, [view, t]);

  const activeTab = tabs.find((tab) => tab.id === activeId) ?? tabs[0];

  return (
    <div>
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        <div className="flex items-center gap-3 flex-wrap">
          {view && view.hiddenByMode > 0 && (
            <span className="text-xs text-gray-500">
              {t('orcaSchemaView.hiddenByLevel', { count: view.hiddenByMode })}
            </span>
          )}
          <SettingModeSelector mode={mode} onChange={onModeChange} />
        </div>
      </div>

      {!view ? (
        <p className="text-gray-400 text-sm">{t('orcaSchemaView.loading')}</p>
      ) : !activeTab ? (
        <p className="text-gray-400 text-sm">{t('orcaSchemaView.emptyAtLevel')}</p>
      ) : (
        <>
          <div className="flex flex-wrap gap-2 mb-4 border-b border-white/20">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveId(tab.id)}
                className={`px-3 sm:px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
                  activeTab.id === tab.id
                    ? 'bg-white/10 text-white border-b-2 border-purple-500'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {tab.title}
              </button>
            ))}
          </div>
          <div className="p-3 sm:p-4 bg-white/5 rounded-xl border border-white/10 space-y-4">
            {activeTab.groups.map((group, index) => (
              <Group key={index} group={group} showKeys={activeTab.id === OTHER_PAGE_ID} />
            ))}
          </div>
        </>
      )}
    </div>
  );
};
