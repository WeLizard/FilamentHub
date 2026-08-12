import { describe, expect, it } from 'vitest';

import { parseWikiGuide } from './wikiGuide';

describe('parseWikiGuide', () => {
  it('separates the introduction, steps, and images of each step', () => {
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
        images: [{
          alt: 'Catalog search',
          src: '/wiki_content/images/guides/catalog.webp',
          callouts: [{ label: 'Type a material name here', x: 82, y: 14 }],
        }],
        content: 'Use the filters and open the exact product variant.',
      },
      {
        id: '2-add-your-spool',
        title: '2. Add your spool',
        images: [],
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

    expect(guide.steps[0].images[0].callouts).toEqual([
      { label: 'Open this control', x: 100, y: 0 },
    ]);
    expect(guide.steps[0].content).toBe('Continue with the form.');
  });

  it('keeps each image paired with only the callouts that follow it', () => {
    const guide = parseWikiGuide(`
## Import a small batch

<!-- guide-media-plan
type: screenshot-sequence
status: integrated
-->

![CSV help](/csv-help.webp)
<!-- guide-callout x=20 y=30: Download the current template -->

![Import result](/csv-result.webp)
<!-- guide-callout x=60 y=70: Review every rejected row -->

Continue only after checking the report.
`);

    expect(guide.steps[0].images).toEqual([
      {
        alt: 'CSV help',
        src: '/csv-help.webp',
        callouts: [{ label: 'Download the current template', x: 20, y: 30 }],
      },
      {
        alt: 'Import result',
        src: '/csv-result.webp',
        callouts: [{ label: 'Review every rejected row', x: 60, y: 70 }],
      },
    ]);
    expect(guide.steps[0].content).toBe('Continue only after checking the report.');
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
