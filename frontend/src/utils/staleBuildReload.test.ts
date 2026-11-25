import { beforeEach, describe, expect, it } from 'vitest';

import { shouldReloadForStaleBuild } from './staleBuildReload';

describe('shouldReloadForStaleBuild', () => {
  beforeEach(() => sessionStorage.clear());

  it('reloads once and not again while the same failure repeats', () => {
    expect(shouldReloadForStaleBuild(sessionStorage, 1_000_000)).toBe(true);
    expect(shouldReloadForStaleBuild(sessionStorage, 1_005_000)).toBe(false);
  });

  it('reloads again for a later release', () => {
    expect(shouldReloadForStaleBuild(sessionStorage, 1_000_000)).toBe(true);
    expect(shouldReloadForStaleBuild(sessionStorage, 1_000_000 + 3_600_000)).toBe(true);
  });
});
