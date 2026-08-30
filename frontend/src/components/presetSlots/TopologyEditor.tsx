import { useTranslation } from 'react-i18next';
import { Dropdown } from '../Dropdown';
import type { FeedTopologyChoice } from './adapters/types';
import { initialTopology } from './adapters/topology';
import type { TopologySelection } from './adapters/topology';

export function TopologyEditor({ choices, value, onChange }: {
  choices: FeedTopologyChoice[];
  value: TopologySelection;
  onChange: (value: TopologySelection) => void;
}) {
  const { t } = useTranslation();
  const choice = choices.find((item) => item.id === value.choice) ?? choices[0];
  const extras = new Set(choice.extras?.map((item) => item.index));
  const actualIndices = value.routes?.filter((item) => !extras.has(item.provider_index)).map((item) => item.provider_index).sort((a, b) => a - b);
  const sparse = actualIndices !== undefined && JSON.stringify(actualIndices)
    !== JSON.stringify(choice.slots(Number(value.count)).map((item) => item.provider_index));
  return <div className="space-y-3">
    {choices.length > 1 && <Dropdown label={t('printerSetup.feed.label')} value={choice.id}
      clearable={false} options={choices.map((item) => ({ value: item.id, label: t(item.labelKey) }))}
      onChange={(id) => onChange(initialTopology(choices.find((item) => item.id === id)!))} />}
    {choice.count && <label className="block text-sm">{t(choice.count.labelKey)}
      <input type="number" min={1} max={choice.count.max} value={value.count} disabled={sparse}
        onChange={(event) => onChange({ ...value, count: event.target.value, routes: undefined })}
        className="mt-1 w-full rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-sm text-white" />
    </label>}
    {choice.count && sparse && <p className="text-xs text-gray-400">{t('printerSetup.feed.existingMap')}</p>}
    {choice.extras?.map((extra) => <label key={extra.index} className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={value.extras.includes(extra.index)} onChange={(event) => onChange({ ...value,
        extras: event.target.checked ? [...value.extras, extra.index] : value.extras.filter((index) => index !== extra.index) })} />
      {t(extra.labelKey)}
    </label>)}
  </div>;
}
