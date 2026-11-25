// Writes public/llms.txt from the capability list and the English texts.
// `--check` fails when the committed file differs, so the description of the
// product cannot drift away from what the site itself says.
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { DEFAULT_LOCALE, buildLlmsTxt, createTranslator } from './public-pages.mjs';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const targetPath = path.join(frontendRoot, 'public', 'llms.txt');

const readJson = async (...segments) => JSON.parse(
  await readFile(path.join(frontendRoot, 'src', ...segments), 'utf8'),
);

export async function renderLlmsTxt() {
  const translator = createTranslator(
    await readJson('locales', DEFAULT_LOCALE, 'translation.json'),
    await readJson('locales', DEFAULT_LOCALE, 'features.json'),
  );
  return buildLlmsTxt(
    translator,
    await readJson('data', 'capabilities.json'),
    await readJson('data', 'siteOrigins.json'),
  );
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const expected = await renderLlmsTxt();
  if (process.argv.includes('--check')) {
    const current = (await readFile(targetPath, 'utf8')).replaceAll('\r\n', '\n');
    if (current !== expected) {
      console.error('public/llms.txt is out of date: run `node scripts/generate-llms.mjs`.');
      process.exit(1);
    }
  } else {
    await writeFile(targetPath, expected, 'utf8');
  }
}
