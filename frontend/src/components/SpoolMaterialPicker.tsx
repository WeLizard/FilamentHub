import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { filamentsAPI, type UserSpool } from '../api/client';
import { useDebounce } from '../hooks/useDebounce';
import type { Filament } from '../types/api';
import { rankSpoolMaterials } from '../utils/spoolMaterialSearch';
import { Dropdown } from './Dropdown';

interface SpoolMaterialPickerProps {
  selected?: Filament;
  shelfSpools: readonly UserSpool[];
  presetMaterials: readonly Filament[];
  onSelect: (material: Filament | null) => void;
  onCreate: () => void;
}

const MAX_SHELF_SUGGESTIONS = 8;

export function SpoolMaterialPicker({
  selected, shelfSpools, presetMaterials, onSelect, onCreate,
}: SpoolMaterialPickerProps) {
  const { t, i18n } = useTranslation();
  const [input, setInput] = useState('');
  const search = useDebounce(input.trim());
  const shelfIds = useMemo(() => [...new Set(shelfSpools
    .filter(spool => spool.state === 'shelf' || spool.state === 'active')
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at) || right.id - left.id)
    .map(spool => spool.filament_id)
    .filter((id): id is number => typeof id === 'number'))], [shelfSpools]);
  const suggestedShelfIds = shelfIds.slice(0, MAX_SHELF_SUGGESTIONS);
  const shelf = useQuery({
    queryKey: ['spool-material-suggestions', suggestedShelfIds],
    queryFn: async () => {
      const results = await Promise.allSettled(suggestedShelfIds.map(id => filamentsAPI.get(id)));
      return results.flatMap(result => result.status === 'fulfilled' ? [result.value] : []);
    },
    enabled: !selected && suggestedShelfIds.length > 0,
    staleTime: 60_000,
  });
  const catalog = useQuery({
    queryKey: ['spool-material-search', search],
    queryFn: ({ signal }) => filamentsAPI.list({
      active_only: true, page: 1, size: 32, search: search || undefined, search_mode: 'identity',
    }, { signal }),
    enabled: !selected,
    staleTime: 30_000,
  });
  const pending = input.trim() !== search || catalog.isLoading || (!search && shelf.isLoading);
  const matches = pending ? [] : rankSpoolMaterials(
    search, shelfIds, shelf.data ?? [], presetMaterials, catalog.data?.items ?? [],
  );
  const label = (material: Filament) => {
    const diameter = material.diameter == null ? null
      : material.diameter.toLocaleString(i18n.resolvedLanguage ?? i18n.language) + ' ' + t('labelStudio.mm');
    return [...new Set([material.brand_name, material.name, material.line_name, material.material_type,
      material.color_name, diameter].filter(Boolean))].join(' · ');
  };
  const options: Array<{ value: number | string; label: string; disabled?: boolean }> = matches.map(({ item }) => ({
    value: item.id, label: label(item),
  }));
  if (pending || catalog.isError || !options.length) {
    const status = pending ? 'catalogSearching' : catalog.isError ? 'catalogUnavailable' : 'catalogNoMatches';
    options.push({ value: 'status', label: t(`profilePage.spoolAddModal.${status}`), disabled: true });
  }
  if (!pending) options.push({ value: 'create', label: t('profilePage.spoolAddModal.catalogCreate') });

  if (selected) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-lg border border-purple-400/40 bg-purple-500/10 px-3 py-2 text-sm">
        <span className="text-white">{label(selected)}</span>
        <button type="button" onClick={() => onSelect(null)} className="shrink-0 text-xs text-purple-300 hover:text-white">
          {t('profilePage.spoolAddModal.catalogChange')}
        </button>
      </div>
    );
  }

  return (
    <Dropdown
      label={t('profilePage.spoolAddModal.catalogLabel')}
      labelClassName="sr-only"
      placeholder={t('profilePage.spoolAddModal.catalogPlaceholder')}
      value=""
      options={options}
      filterable
      externallyFiltered
      selectFirstOnEnter={false}
      filterValue={input}
      onFilterChange={setInput}
      onChange={(value) => {
        if (value === 'create') onCreate();
        const match = matches.find(({ item }) => item.id === value);
        if (match) onSelect(match.item);
      }}
      renderOption={(option) => {
        if (option.value === 'create') {
          return <span className="inline-flex items-center gap-1.5 text-purple-300"><Plus className="h-4 w-4" />{option.label}</span>;
        }
        const match = matches.find(({ item }) => item.id === option.value);
        if (!match) return option.label;
        return (
          <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            {match.item.color_hex && <span aria-hidden="true" className="h-3 w-3 shrink-0 rounded-full border border-white/30" style={{ backgroundColor: match.item.color_hex }} />}
            <span>{option.label}</span>
            {match.origin !== 'catalog' && <span className="text-xs text-purple-300">{t(match.origin === 'shelf' ? 'profilePage.spoolAddModal.catalogShelf' : 'profilePage.spoolAddModal.catalogPreset')}</span>}
            {match.similar && <span className="text-xs text-gray-400">{t('profilePage.spoolAddModal.catalogSimilar')}</span>}
          </span>
        );
      }}
    />
  );
}
