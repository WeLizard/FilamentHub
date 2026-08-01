import { describe, expect, it } from 'vitest';
import en from '../locales/en/translation.json';
import ru from '../locales/ru/translation.json';
import zh from '../locales/zh/translation.json';

type Catalog = Record<string, unknown>;

const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;
const SIMPLE_PLACEHOLDER = /{{\s*([A-Za-z0-9_]+)\s*}}/g;

/**
 * The Russian legal editions were published on 2026-08-01 and the other
 * languages follow one whole document at a time. Each line leaves this list
 * when its translation lands; nothing but the legal lag belongs here.
 */
const AWAITING_LEGAL_TRANSLATION = [
  'consentPage.sections.general.personalData.sellerProfile',
  'privacyPage.sections.authRegion.paragraphs',
  'privacyPage.sections.authRegion.title',
  'privacyPage.sections.dataLocation.paragraphs',
  'privacyPage.sections.dataLocation.title',
];

/** Dropped from the Russian terms; they leave the other languages with the same retranslation. */
const SUPERSEDED_BY_RUSSIAN_EDITION = [
  'termsPage.sections.terms.items.moderator',
  'termsPage.sections.terms.items.paidServices',
];

function flatten(node: Catalog, prefix = '', into = new Map<string, unknown>()): Map<string, unknown> {
  for (const [name, value] of Object.entries(node)) {
    const key = `${prefix}${name}`;
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      flatten(value as Catalog, `${key}.`, into);
    } else {
      into.set(key, value);
    }
  }
  return into;
}

/** Plural forms differ per language, so parity is compared on the key without its form suffix. */
function baseKeys(catalog: Map<string, unknown>): Set<string> {
  return new Set([...catalog.keys()].map((key) => key.replace(PLURAL_SUFFIX, '')));
}

function placeholders(value: unknown): Set<string> {
  if (typeof value !== 'string') return new Set();
  return new Set([...value.matchAll(SIMPLE_PLACEHOLDER)].map((match) => match[1]));
}

function shapeOf(value: unknown): string {
  return Array.isArray(value) ? 'array' : typeof value;
}

interface ParityReport {
  missing: string[];
  stale: string[];
  placeholderMismatch: string[];
  shapeMismatch: string[];
}

function compare(reference: Map<string, unknown>, candidate: Map<string, unknown>): ParityReport {
  const referenceBase = baseKeys(reference);
  const candidateBase = baseKeys(candidate);
  const shared = [...candidate.entries()].filter(([key]) => reference.has(key));

  return {
    missing: [...referenceBase].filter((key) => !candidateBase.has(key)),
    stale: [...candidateBase].filter((key) => !referenceBase.has(key)),
    placeholderMismatch: shared
      .filter(([key, value]) => {
        const expected = placeholders(reference.get(key));
        const actual = placeholders(value);
        return expected.size !== actual.size || [...expected].some((name) => !actual.has(name));
      })
      .map(([key]) => key),
    shapeMismatch: shared
      .filter(([key, value]) => shapeOf(reference.get(key)) !== shapeOf(value))
      .map(([key]) => key),
  };
}

const russian = flatten(ru as unknown as Catalog);
const reports: [string, ParityReport][] = [
  ['en', compare(russian, flatten(en as unknown as Catalog))],
  ['zh', compare(russian, flatten(zh as unknown as Catalog))],
];

describe.each(reports)('%s translation', (_language, report) => {
  it('carries every key the interface has in Russian', () => {
    expect(report.missing.filter((key) => !AWAITING_LEGAL_TRANSLATION.includes(key))).toEqual([]);
  });

  it('keeps no key that Russian has already dropped', () => {
    expect(report.stale.filter((key) => !SUPERSEDED_BY_RUSSIAN_EDITION.includes(key))).toEqual([]);
  });

  it('interpolates the same values as Russian', () => {
    expect(report.placeholderMismatch).toEqual([]);
  });

  it('stores every value in the same shape as Russian', () => {
    expect(report.shapeMismatch).toEqual([]);
  });
});

describe('parity exceptions', () => {
  it('lists only keys that are still out of sync', () => {
    const resolved = AWAITING_LEGAL_TRANSLATION.filter(
      (key) => !reports.some(([, report]) => report.missing.includes(key)),
    );
    const removed = SUPERSEDED_BY_RUSSIAN_EDITION.filter(
      (key) => !reports.some(([, report]) => report.stale.includes(key)),
    );
    expect({ resolved, removed }).toEqual({ resolved: [], removed: [] });
  });
});

describe('the comparison itself', () => {
  const reference = flatten({
    page: { title: 'Заголовок', hint: 'Привет, {{name}}', items: ['a', 'b'] },
    countWord_one: 'катушка',
    countWord_few: 'катушки',
  });

  it('reports a key that only Russian has', () => {
    const report = compare(reference, flatten({ page: { title: 'Title', hint: 'Hi, {{name}}', items: ['a'] } }));
    expect(report.missing).toContain('countWord');
    expect(report.stale).toEqual([]);
  });

  it('accepts a language with different plural forms', () => {
    const report = compare(
      reference,
      flatten({
        page: { title: 'Title', hint: 'Hi, {{name}}', items: ['a'] },
        countWord_other: 'spools',
      }),
    );
    expect(report.missing).toEqual([]);
  });

  it('reports a dropped placeholder and a changed shape', () => {
    const report = compare(
      reference,
      flatten({
        page: { title: 'Title', hint: 'Hi there', items: 'a, b' },
        countWord_other: 'spools',
      }),
    );
    expect(report.placeholderMismatch).toEqual(['page.hint']);
    expect(report.shapeMismatch).toEqual(['page.items']);
  });
});
