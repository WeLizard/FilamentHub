/** Pretty viewer for OrcaSlicer settings with a Table / JSON toggle.
 *
 * Renders an arbitrary orcaslicer_settings dict (printer or print profile) as
 * a grouped, human-readable table, while keeping the raw JSON available behind
 * a toggle. Group/label heuristics are best-effort — unknown keys fall back to
 * a humanized version of the snake_case key.
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  settings: Record<string, unknown> | null | undefined;
}

// Known key -> friendly label. Not exhaustive; unknown keys are humanized.
const KEY_LABELS: Record<string, string> = {
  nozzle_diameter: 'Nozzle diameter',
  printable_height: 'Printable height',
  printable_area: 'Printable area',
  gcode_flavor: 'G-code flavor',
  retraction_length: 'Retraction length',
  retraction_speed: 'Retraction speed',
  z_hop: 'Z hop',
  layer_height: 'Layer height',
  initial_layer_print_height: 'First layer height',
  wall_loops: 'Wall loops',
  sparse_infill_density: 'Infill density',
  sparse_infill_pattern: 'Infill pattern',
  top_shell_layers: 'Top shell layers',
  bottom_shell_layers: 'Bottom shell layers',
  outer_wall_speed: 'Outer wall speed',
  inner_wall_speed: 'Inner wall speed',
  sparse_infill_speed: 'Infill speed',
  enable_support: 'Supports enabled',
};

function humanize(key: string): string {
  if (KEY_LABELS[key]) return KEY_LABELS[key];
  const s = key.replace(/_/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) return value.map((v) => String(v)).join(', ') || '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

type Group = 'machine' | 'retraction' | 'speed' | 'temperature' | 'walls' | 'other';

function groupOf(key: string): Group {
  if (key.startsWith('machine_') || key === 'gcode_flavor' || key.startsWith('printable_') || key === 'nozzle_diameter')
    return 'machine';
  if (key.startsWith('retraction') || key === 'z_hop' || key === 'wipe') return 'retraction';
  if (key.includes('temp')) return 'temperature';
  if (key.includes('wall') || key.includes('shell') || key.includes('infill') || key.includes('layer')) return 'walls';
  if (key.includes('speed') || key.includes('acceleration')) return 'speed';
  return 'other';
}

const GROUP_ORDER: Group[] = ['machine', 'walls', 'speed', 'retraction', 'temperature', 'other'];

export const OrcaSettingsView: React.FC<Props> = ({ settings }) => {
  const { t } = useTranslation();
  const [raw, setRaw] = useState(false);

  const entries = useMemo(() => Object.entries(settings ?? {}), [settings]);

  const grouped = useMemo(() => {
    const map = new Map<Group, [string, unknown][]>();
    for (const [k, v] of entries) {
      const g = groupOf(k);
      if (!map.has(g)) map.set(g, []);
      map.get(g)!.push([k, v]);
    }
    for (const arr of map.values()) arr.sort((a, b) => a[0].localeCompare(b[0]));
    return map;
  }, [entries]);

  const isEmpty = entries.length === 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-sm font-semibold text-white">{t('profilePage.orcaSlicerSettings')}</h4>
        <div className="flex rounded-lg border border-white/15 overflow-hidden text-xs">
          <button
            type="button"
            onClick={() => setRaw(false)}
            className={`px-2.5 py-1 transition-colors ${!raw ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'}`}
          >
            {t('orcaSettings.table')}
          </button>
          <button
            type="button"
            onClick={() => setRaw(true)}
            className={`px-2.5 py-1 transition-colors ${raw ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'}`}
          >
            {t('orcaSettings.json')}
          </button>
        </div>
      </div>

      {isEmpty ? (
        <p className="text-sm text-gray-500">{t('orcaSettings.empty')}</p>
      ) : raw ? (
        <pre className="bg-black/40 border border-white/10 rounded-xl p-4 text-xs text-gray-200 overflow-auto max-h-72 whitespace-pre">
          {JSON.stringify(settings ?? {}, null, 2)}
        </pre>
      ) : (
        <div className="space-y-4">
          {GROUP_ORDER.filter((g) => grouped.has(g)).map((g) => (
            <div key={g}>
              <div className="text-[11px] uppercase tracking-wide text-purple-300/80 mb-1.5">
                {t(`orcaSettings.group.${g}`)}
              </div>
              <div className="rounded-xl border border-white/10 overflow-hidden">
                {grouped.get(g)!.map(([k, v], idx) => (
                  <div
                    key={k}
                    className={`flex items-start gap-3 px-3 py-1.5 text-sm ${idx % 2 === 0 ? 'bg-white/[0.03]' : ''}`}
                  >
                    <span className="text-gray-400 min-w-[200px] shrink-0">{humanize(k)}</span>
                    <span className="text-white break-all">{formatValue(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
