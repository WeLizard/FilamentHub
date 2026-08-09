import { describe, expect, it } from 'vitest';

import { parseWikiGuide } from './wikiGuide';

describe('parseWikiGuide', () => {
  it('separates the introduction, steps, and the primary image of each step', () => {
    const guide = parseWikiGuide(`
Short introduction.

## 1. Find a material

![Catalog search](/wiki_content/images/guides/catalog.webp)
<!-- guide-callout x=82 y=14: Type a material name here -->

Use the filters and open the exact product variant.

## 2. Add your spool

Record the physical spool separately.
`);

    expect(guide.intro).toBe('Short introduction.');
    expect(guide.steps).toEqual([
      {
        id: '1-find-a-material',
        title: '1. Find a material',
        image: {
          alt: 'Catalog search',
          src: '/wiki_content/images/guides/catalog.webp',
          callouts: [{ label: 'Type a material name here', x: 82, y: 14 }],
        },
        content: 'Use the filters and open the exact product variant.',
      },
      {
        id: '2-add-your-spool',
        title: '2. Add your spool',
        image: null,
        content: 'Record the physical spool separately.',
      },
    ]);
  });

  it('keeps a non-journey guide readable as a regular body', () => {
    expect(parseWikiGuide('A short guide without steps.')).toEqual({
      intro: 'A short guide without steps.',
      steps: [],
    });
  });

  it('keeps callouts inside the image bounds and out of article content', () => {
    const guide = parseWikiGuide(`
## Step

![Screen](/screen.webp)
<!-- guide-callout x=120 y=0: Open this control -->

Continue with the form.
`);

    expect(guide.steps[0].image?.callouts).toEqual([
      { label: 'Open this control', x: 100, y: 0 },
    ]);
    expect(guide.steps[0].content).toBe('Continue with the form.');
  });

  it('removes the repeated article title from the guide introduction', () => {
    const guide = parseWikiGuide(`
# From shelf to print

The guide introduction.

## 1. Start

Continue here.
`);

    expect(guide.intro).toBe('The guide introduction.');
  });
});
