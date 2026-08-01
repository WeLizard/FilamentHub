import { describe, expect, it } from 'vitest';

import { buildWikiLineDiff } from './WikiRevisionDiff';

describe('buildWikiLineDiff', () => {
  it('keeps line numbers aligned around additions and removals', () => {
    const result = buildWikiLineDiff(
      ['# Title', '', 'Old paragraph', 'Shared ending'].join('\n'),
      ['# Title', '', 'New paragraph', 'Extra detail', 'Shared ending'].join('\n'),
    );

    expect(result).toEqual([
      { kind: 'equal', text: '# Title', beforeLine: 1, afterLine: 1 },
      { kind: 'equal', text: '', beforeLine: 2, afterLine: 2 },
      { kind: 'removed', text: 'Old paragraph', beforeLine: 3, afterLine: null },
      { kind: 'added', text: 'New paragraph', beforeLine: null, afterLine: 3 },
      { kind: 'added', text: 'Extra detail', beforeLine: null, afterLine: 4 },
      { kind: 'equal', text: 'Shared ending', beforeLine: 4, afterLine: 5 },
    ]);
  });

  it('returns only equal lines for identical content', () => {
    expect(buildWikiLineDiff('same\ntext', 'same\ntext')).toEqual([
      { kind: 'equal', text: 'same', beforeLine: 1, afterLine: 1 },
      { kind: 'equal', text: 'text', beforeLine: 2, afterLine: 2 },
    ]);
  });
});
