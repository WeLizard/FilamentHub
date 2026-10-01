import { fireEvent, render, screen, within } from '@testing-library/react';
import { createInstance } from 'i18next';
import { useState } from 'react';
import { I18nextProvider } from 'react-i18next';
import { describe, expect, it } from 'vitest';
import schemaJson from '../data/orcaPresetSchema.filament.json';
import type { SettingMode } from '../data/orcaFieldModes';
import en from '../locales/en/translation.json';
import ru from '../locales/ru/translation.json';
import zh from '../locales/zh/translation.json';
import type { OrcaPresetSchema } from '../utils/orcaPresetSchema';
import { buildSchemaView, isOrcaServiceKey, type FieldView, type SchemaView } from '../utils/orcaSchemaView';
import { OrcaSchemaSettingsView } from './OrcaSchemaSettingsView';

const schema = schemaJson as unknown as OrcaPresetSchema;

// Shaped like production preset 185: Orca-serialised values, per-plate bed temperatures that differ.
const PRESET: Record<string, unknown> = {
  activate_air_filtration: ['1'],
  activate_chamber_temp_control: ['0'],
  adaptive_pressure_advance: ['0'],
  adaptive_pressure_advance_model: ['"0,0,0\\n0,0,0"'],
  additional_cooling_fan_speed: ['70'],
  chamber_temperature: ['0'],
  close_fan_the_first_x_layers: ['3'],
  cool_plate_temp: ['35'],
  cool_plate_temp_initial_layer: ['35'],
  default_filament_colour: ['"#00FF73"'],
  eng_plate_temp: ['0'],
  eng_plate_temp_initial_layer: ['0'],
  fan_max_speed: ['80'],
  fan_min_speed: ['10'],
  filament_adaptive_volumetric_speed: ['0,0'],
  filament_cost: ['24.99'],
  filament_density: ['1.26'],
  filament_diameter: ['1.75'],
  filament_extruder_variant: ['Direct Drive Standard', 'Direct Drive High Flow'],
  filament_flow_ratio: ['1'],
  filament_ironing_flow: ['nil,nil'],
  filament_ironing_inset: ['nil,nil'],
  filament_ironing_spacing: ['nil,nil'],
  filament_ironing_speed: ['nil,nil'],
  filament_max_volumetric_speed: ['28.6'],
  filament_ramming_parameters: ['"120 100 6.6 6.8|0.05 6.6 0.45 6.8"'],
  filament_retract_before_wipe: ['nil,nil%'],
  filament_retraction_length: ['nil,nil'],
  filament_shrink: ['100%'],
  filament_start_gcode: ['"M117 start\\nG92 E0\\nM104 S0"'],
  filament_tower_interface_pre_extrusion_dist: ['10'],
  filament_tower_interface_print_temp: ['-1'],
  filament_tower_ironing_area: ['4'],
  filament_type: ['PLA'],
  filament_vendor: ['"Bambu Lab"'],
  filament_z_hop_types: ['nil,nil'],
  hot_plate_temp: ['85'],
  hot_plate_temp_initial_layer: ['85'],
  idle_temperature: ['170'],
  nozzle_temperature: ['240'],
  nozzle_temperature_initial_layer: ['245'],
  nozzle_temperature_range_high: ['280'],
  nozzle_temperature_range_low: ['240'],
  overhang_fan_threshold: ['50%'],
  pressure_advance: ['0.02'],
  required_nozzle_HRC: ['3'],
  supertack_plate_temp: ['85'],
  supertack_plate_temp_initial_layer: ['85'],
  temperature_vitrification: ['45'],
  textured_cool_plate_temp: ['35'],
  textured_cool_plate_temp_initial_layer: ['35'],
  textured_plate_temp: ['55'],
  textured_plate_temp_initial_layer: ['55'],
  volumetric_speed_coefficients: ['"0 0 0 0 0 0";"0 0 0 0 0 0"'],
  // Not defined by the schema at all.
  customized_plate_temp: ['85'],
  vendor_x_custom_param: ['7'],
  // Service keys that stay hidden.
  compatible_printers: [],
  compatible_printers_condition: '',
  derived_from_external_id: 'abc',
  fhub_id: '185',
  inherits: 'Bambu PLA Basic @BBL P2S',
};

const collectKeys = (view: SchemaView): Set<string> => {
  const keys = new Set<string>();
  const add = (field: FieldView | null) => field && keys.add(field.key);
  for (const page of view.pages) {
    for (const group of page.groups) {
      for (const row of group.rows) {
        if (row.type === 'field') add(row.field);
        if (row.type === 'line') row.fields.forEach(add);
        if (row.type === 'table') row.rows.forEach((tableRow) => tableRow.cells.forEach(add));
      }
    }
  }
  view.other.forEach(add);
  return keys;
};

const makeI18n = async (language: string) => {
  const i18n = createInstance();
  await i18n.init({
    lng: language,
    resources: { en: { translation: en }, ru: { translation: ru }, zh: { translation: zh } },
  });
  return i18n;
};

const Harness = ({ initial = 'simple' }: { initial?: SettingMode }) => {
  const [mode, setMode] = useState<SettingMode>(initial);
  return <OrcaSchemaSettingsView title="Settings" settings={PRESET} mode={mode} onModeChange={setMode} schema={schema} />;
};

const renderView = async (language: string, initial: SettingMode = 'simple') => {
  const i18n = await makeI18n(language);
  return render(<I18nextProvider i18n={i18n}><Harness initial={initial} /></I18nextProvider>);
};

describe('Orca schema preset view', () => {
  it('shows every stored key at Expert level except the reviewed service keys', () => {
    const shown = collectKeys(buildSchemaView(schema, PRESET, 'expert', 'en'));
    const missing = Object.keys(PRESET).filter((key) => !shown.has(key) && !isOrcaServiceKey(key));
    expect(missing).toEqual([]);
    expect(shown.has('inherits')).toBe(false);
    expect(shown.has('fhub_id')).toBe(false);
    expect(shown.has('compatible_printers')).toBe(false);
    // Keys unknown to the schema are not dropped.
    expect(shown.has('vendor_x_custom_param')).toBe(true);
    expect(shown.has('customized_plate_temp')).toBe(true);
  });

  it('reads values the way Orca serialises them', () => {
    const view = buildSchemaView(schema, PRESET, 'expert', 'en');
    const field = (key: string): FieldView => {
      const found = [...view.pages.flatMap((p) => p.groups.flatMap((g) => g.rows)), ...view.other.map((f) => ({ type: 'field' as const, field: f }))]
        .flatMap((row) => (row.type === 'field' ? [row.field] : row.type === 'line' ? row.fields : row.rows.flatMap((r) => r.cells)))
        .find((f) => f?.key === key);
      return found as FieldView;
    };
    expect(field('filament_vendor').cells).toEqual([{ kind: 'text', text: 'Bambu Lab' }]);
    expect(field('filament_retract_before_wipe').cells).toEqual([{ kind: 'nil' }]);
    expect(field('adaptive_pressure_advance_model').cells).toEqual([{ kind: 'block', text: '0,0,0\n0,0,0' }]);
    expect(field('volumetric_speed_coefficients').cells).toEqual([{ kind: 'text', text: '0 0 0 0 0 0' }]);
    expect(field('filament_extruder_variant').cells).toHaveLength(2);
  });

  it('counts what the level hides and reveals it on the next level', () => {
    const simple = buildSchemaView(schema, PRESET, 'simple', 'en');
    const advanced = buildSchemaView(schema, PRESET, 'advanced', 'en');
    const expert = buildSchemaView(schema, PRESET, 'expert', 'en');
    expect(simple.hiddenByMode).toBeGreaterThan(advanced.hiddenByMode);
    expect(advanced.hiddenByMode).toBeGreaterThan(0);
    expect(expert.hiddenByMode).toBe(0);
    expect(collectKeys(simple).size + simple.hiddenByMode).toBe(collectKeys(expert).size);
  });

  it('switches level from the selector and reports the hidden count', async () => {
    await renderView('en');
    expect(screen.getByText(/Hidden at this level: \d+/)).toBeInTheDocument();
    expect(screen.queryByText('Required nozzle HRC')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Expert' }));

    expect(screen.queryByText(/Hidden at this level/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Other parameters' }));
    expect(screen.getByText('Vendor x custom param')).toBeInTheDocument();
  });

  it('shows each plate with its own temperature and marks unsupported plates', async () => {
    await renderView('en');
    const table = screen.getByRole('table');
    const textured = within(within(table).getByText('Textured PEI Plate').closest('tr')!);
    expect(textured.getAllByText('55')).toHaveLength(2);
    expect(textured.queryByText('85')).not.toBeInTheDocument();
    const engineering = within(within(table).getByText('Engineering Plate').closest('tr')!);
    expect(engineering.getAllByText('Not for this plate')).toHaveLength(2);
  });

  it('uses Orca Russian titles and labels when the site language is Russian', async () => {
    await renderView('ru');
    expect(screen.getByRole('button', { name: 'Материал' })).toBeInTheDocument();
    expect(screen.getByText('Подогрев покрытия стола')).toBeInTheDocument();
    expect(screen.getAllByText('Не для этого покрытия').length).toBeGreaterThan(0);
    expect(screen.queryByText('Bed temperature')).not.toBeInTheDocument();
  });
});
