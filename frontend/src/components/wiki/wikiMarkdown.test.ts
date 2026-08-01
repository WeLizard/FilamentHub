import { describe, expect, it } from 'vitest';

import { plainWikiSummary, withoutLeadingArticleHeading } from './wikiMarkdown';


describe('Wiki Markdown presentation helpers', () => {
  it('removes the body H1 already represented by the article title', () => {
    expect(withoutLeadingArticleHeading('# Article title\n\n## First section\nBody')).toBe('## First section\nBody');
  });

  it('turns a legacy generated summary into one plain paragraph', () => {
    expect(plainWikiSummary('# Full guide\n\n## Introduction\n\n**Warping** bends a printed part.')).toBe(
      'Warping bends a printed part.',
    );
  });
});
