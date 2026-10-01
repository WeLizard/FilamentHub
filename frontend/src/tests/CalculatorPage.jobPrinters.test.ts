import { describe, expect, it } from 'vitest';

import type { CalculatorGcodeParseResponse } from '../types/api';
import {
  appendJobConfigs,
  createJobConfigs,
  jobPrinterNote,
  pluginSliceJobStates,
  pluginSliceJobs,
  type CalculatorJobConfig,
  type ParsedJobState,
} from '../pages/CalculatorPage';

const job = (key: string, suggested?: number[]): ParsedJobState => ({
  key,
  parsed: {
    file_name: `${key}.gcode`,
    file_size_bytes: 1,
    print_time_seconds: 60,
    object_groups: [],
    materials: [],
    suggested_physical_printer_ids: suggested,
  } as CalculatorGcodeParseResponse,
});

describe('printer of a plate, taken from the file', () => {
  it('gives a plate its printer only when exactly one of the user\'s printers fits', () => {
    const configs = createJobConfigs([job('one', [7]), job('two', [7, 8]), job('none', []), job('old')], true);

    expect(configs.map((config) => config.physicalPrinterId)).toEqual([7, '', '', '']);
  });

  it('leaves a lone plate on the order-wide printer', () => {
    expect(createJobConfigs([job('one', [7])], false)[0].physicalPrinterId).toBe('');
  });

  it('keeps the printer a person already chose when more plates arrive', () => {
    const chosen: CalculatorJobConfig = { ...createJobConfigs([job('first', [7])], false)[0], physicalPrinterId: 9 };

    const next = appendJobConfigs([chosen], [job('second', [7]), job('third', [7, 8])]);

    expect(next.map((config) => [config.jobKey, config.physicalPrinterId])).toEqual([
      ['first', 9],
      ['second', 7],
      ['third', ''],
    ]);
  });

  it('asks for a choice only while several printers fit and none is chosen', () => {
    const several = job('a', [7, 8]);
    const [config] = createJobConfigs([several], true);

    expect(jobPrinterNote(several, config)).toBe('several');
    expect(jobPrinterNote(several, { ...config, physicalPrinterId: 8 })).toBe('default');

    const single = job('b', [7]);
    const [matched] = createJobConfigs([single], true);
    expect(jobPrinterNote(single, matched)).toBe('fromFile');
    expect(jobPrinterNote(single, { ...matched, physicalPrinterId: 9 })).toBe('default');
  });
});

describe('plates of a slice the plugin read', () => {
  const plate = (index: number) => ({ plate_index: index, file_name: 'x.gcode.3mf' });

  it('takes every plate when the plugin sends them, whatever the old single job says', () => {
    expect(pluginSliceJobs({ jobs: [plate(1), plate(2)], parsed: plate(1) })).toEqual([plate(1), plate(2)]);
  });

  it('still takes the single job of a plugin that predates plates', () => {
    expect(pluginSliceJobs({ parsed: plate(1) })).toEqual([plate(1)]);
  });

  it('takes nothing from an answer that carries no usable job', () => {
    expect(pluginSliceJobs({ error: 'http', status: 413 })).toEqual([]);
    expect(pluginSliceJobs({ jobs: 'x', parsed: null })).toEqual([]);
    expect(pluginSliceJobs({ jobs: [null, 3, plate(2)] })).toEqual([plate(2)]);
  });

  it('gives every plate of a slice the machine the slice was made for', () => {
    const plates = [plate(1), plate(2)] as CalculatorGcodeParseResponse[];

    const states = pluginSliceJobStates(plates, { physical_printer_id: 147, printer_profile_id: 5 });

    expect(states.map((state) => state.parsed.suggested_physical_printer_ids)).toEqual([[147], [147]]);
    expect(states.map((state) => state.printerProfileId)).toEqual([5, 5]);
    expect(new Set(states.map((state) => state.key)).size).toBe(2);
    // A slice for an unknown machine keeps what the server suggested.
    expect(pluginSliceJobStates(plates, { physical_printer_id: null, printer_profile_id: null })[0].parsed)
      .toBe(plates[0]);
  });
});
