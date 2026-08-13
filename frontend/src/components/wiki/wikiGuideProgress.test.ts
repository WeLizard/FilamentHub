import { beforeEach, describe, expect, it } from 'vitest';

import {
  getCompletedWikiGuideIds,
  markWikiGuideCompleted,
  mergeCompletedWikiGuideIds,
  WIKI_GUIDE_PROGRESS_STORAGE_KEY,
} from './wikiGuideProgress';

describe('wiki guide progress', () => {
  beforeEach(() => localStorage.clear());

  it('stores completed guide ids without losing earlier progress', () => {
    markWikiGuideCompleted('user:shelf');
    markWikiGuideCompleted('brand:materials');

    expect([...getCompletedWikiGuideIds()]).toEqual([
      'user:shelf',
      'brand:materials',
    ]);
  });

  it('merges account progress without losing local completion markers', () => {
    markWikiGuideCompleted('user:shelf');

    expect([...mergeCompletedWikiGuideIds(['article:catalog-material'])]).toEqual([
      'user:shelf',
      'article:catalog-material',
    ]);
  });

  it('ignores corrupt stored data and invalid ids', () => {
    localStorage.setItem(WIKI_GUIDE_PROGRESS_STORAGE_KEY, '{broken');
    markWikiGuideCompleted('not valid/id');

    expect(getCompletedWikiGuideIds().size).toBe(0);
  });
});
