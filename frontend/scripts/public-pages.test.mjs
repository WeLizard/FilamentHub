// @vitest-environment node
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { renderLlmsTxt } from './generate-llms.mjs';
import { buildPublicPages, createTranslator, renderPageBody } from './public-pages.mjs';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const readJson = async (...segments) => JSON.parse(
  await readFile(path.join(frontendRoot, ...segments), 'utf8'),
);

describe('public pages', () => {
  it('describes every capability in every language', async () => {
    // A capability added to the list without its text in one language would
    // otherwise surface only as a failed production build.
    const capabilities = await readJson('src', 'data', 'capabilities.json');
    for (const locale of ['en', 'ru', 'zh']) {
      const t = createTranslator(
        await readJson('src', 'locales', locale, 'translation.json'),
        await readJson('src', 'locales', locale, 'features.json'),
      );
      // A missing text throws, so building the pages proves the language is complete.
      const pages = buildPublicPages(t, capabilities);
      const about = pages.find((page) => page.path === '/about');
      const roadmap = about.blocks.filter(([type]) => type === 'ul').flatMap(([, items]) => items);

      expect(roadmap).toHaveLength(capabilities.items.length);
    }
  });

  it('keeps the three languages of the product description in step', async () => {
    // The interface strings have a parity test; these files are loaded next to them.
    const shape = (node) => (
      node !== null && typeof node === 'object' && !Array.isArray(node)
        ? Object.fromEntries(Object.entries(node).map(([key, value]) => [key, shape(value)]))
        : Array.isArray(node) ? node.length : typeof node
    );
    const [en, ru, zh] = await Promise.all(
      ['en', 'ru', 'zh'].map((locale) => readJson('src', 'locales', locale, 'features.json')),
    );

    expect(shape(ru)).toEqual(shape(en));
    expect(shape(zh)).toEqual(shape(en));
    // The loader merges both files at the top level: a shared key would replace a whole section.
    const interfaceKeys = Object.keys(await readJson('src', 'locales', 'en', 'translation.json'));
    expect(Object.keys(en).filter((key) => interfaceKeys.includes(key))).toEqual([]);
  });

  it('writes page text as text', () => {
    const body = renderPageBody(
      { blocks: [['p', '<b>$& "quoted"'], ['ul', [{ href: '/a"b', label: '<i>', text: '&' }]]] },
      (href) => `/ru${href}`,
    );

    expect(body).toContain('<p>&lt;b&gt;$&amp; &quot;quoted&quot;</p>');
    expect(body).toContain('<a href="/ru/a&quot;b">&lt;i&gt;</a>: &amp;');
  });

  it('sends every feature group to its own destination', async () => {
    // The features page was once withdrawn because several cards led to the
    // same page; a group must say where its own next step is.
    const { groups } = await readJson('src', 'data', 'capabilities.json');
    const links = groups.map((group) => group.link);

    expect(new Set(links).size).toBe(links.length);
  });

  it('keeps the committed llms.txt in step with the capability list', async () => {
    const committed = await readFile(path.join(frontendRoot, 'public', 'llms.txt'), 'utf8');

    expect(committed.replaceAll('\r\n', '\n')).toBe(await renderLlmsTxt());
  });
});
