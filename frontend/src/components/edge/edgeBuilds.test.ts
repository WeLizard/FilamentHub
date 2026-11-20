import { describe, expect, it } from 'vitest';
import en from '../../locales/en/translation.json';
import ru from '../../locales/ru/translation.json';
import zh from '../../locales/zh/translation.json';
import {
  composeEdgeBuild,
  EDGE_ENCLOSURE_FILES,
  EDGE_ENCLOSURE_IMAGES,
  EDGE_ENCLOSURE_INSIDE_IMAGES,
  EDGE_PIN_MAPS,
  EDGE_PRESETS,
  EDGE_RESERVED_PINS,
  edgeFixOptions,
  edgeOptionProblem,
  type EdgeBuildOptions,
} from './edgeBuilds';

const MCUS = ['c3', 's3'] as const;
const DISPLAYS = ['none', 'oled', 'touch'] as const;
const POWERS = ['usb', 'battery', 'printer'] as const;
const FLAGS = [false, true];

function allOptions(): EdgeBuildOptions[] {
  const result: EdgeBuildOptions[] = [];
  for (const mcu of MCUS) for (const display of DISPLAYS) for (const power of POWERS)
    for (const feedback of FLAGS) for (const keys of FLAGS) for (const climate of FLAGS)
      result.push({ mcu, display, power, feedback, keys, climate });
  return result;
}
const possible = allOptions().filter((options) => !edgeOptionProblem(options));

function lookup(tree: unknown, key: string): unknown {
  return key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], tree);
}

describe('Edge builds', () => {
  // A wiring diagram that puts two signals on one GPIO would burn a module or
  // silently break the build for everyone who follows it.
  it('never puts two signals on one pad or uses a reserved pad', () => {
    for (const options of possible) {
      const build = composeEdgeBuild(options);
      const reserved = EDGE_RESERVED_PINS[options.mcu].map((pad) => `GPIO${pad}`);
      const signalOf = new Map<string, string>();
      for (const module of build.modules) {
        for (const pin of module.pins) {
          if (!pin.signal) continue;
          const pad = `GPIO${EDGE_PIN_MAPS[options.mcu][pin.signal]}`;
          expect(reserved, `${JSON.stringify(options)} ${pin.signal}`).not.toContain(pad);
          const other = signalOf.get(pad);
          expect(other === undefined || other === pin.signal, `${JSON.stringify(options)} ${pad}: ${other} and ${pin.signal}`).toBe(true);
          signalOf.set(pad, pin.signal);
        }
      }
    }
  });

  it('fixes every impossible choice into a possible one', () => {
    for (const options of allOptions()) {
      for (const changed of Object.keys(options) as (keyof EdgeBuildOptions)[]) {
        const fixed = edgeFixOptions(options, changed);
        expect(edgeOptionProblem(fixed), JSON.stringify({ options, changed })).toBeNull();
        if (!edgeOptionProblem(options)) expect(fixed).toEqual(options);
      }
    }
  });

  it('keeps presets possible and only the released kit marked as having firmware', () => {
    for (const preset of EDGE_PRESETS) {
      expect(edgeOptionProblem(preset.options)).toBeNull();
      expect(composeEdgeBuild(preset.options).firmware).toBe(preset.status === 'prototype');
    }
    expect(possible.filter((options) => composeEdgeBuild(options).firmware)).toHaveLength(1);
  });

  // Every combination renders text from keys; a missing one shows a raw key to users.
  it('has every text a build can show in all three languages', () => {
    const keys = new Set<string>();
    for (const options of possible) {
      const build = composeEdgeBuild(options);
      build.notes.forEach((note) => keys.add(note));
      build.modules.forEach((module) => module.note && keys.add(module.note));
      build.parts.forEach((part) => keys.add(`edgeBuilds.parts.${part.key}`));
      build.powerPath.forEach((stage) => keys.add(`edgeBuilds.power.${stage}.name`));
      if (build.enclosure) keys.add(`edgeBuilds.enclosures.${build.enclosure}.text`);
    }
    for (const files of Object.values(EDGE_ENCLOSURE_FILES)) files.forEach(({ key }) => keys.add(`edgeBuilds.files.${key}`));
    for (const preset of EDGE_PRESETS) keys.add(`edgeBuilds.presets.${preset.id}.text`);
    for (const [locale, tree] of Object.entries({ ru, en, zh })) {
      for (const key of keys) expect(typeof lookup(tree, key), `${locale}: ${key}`).toBe('string');
    }
  });

  it('links only enclosure files that are published', () => {
    // Lazy globs list the files without loading them.
    const published = new Set(Object.keys(import.meta.glob('../../../public/edge-kit/*')).map((path) => path.split('/').pop()));
    const files = [...Object.values(EDGE_ENCLOSURE_FILES).flat().map(({ file }) => file), ...Object.values(EDGE_ENCLOSURE_IMAGES), ...Object.values(EDGE_ENCLOSURE_INSIDE_IMAGES)];
    for (const file of files) expect(published.has(file), file).toBe(true);
  });
});
