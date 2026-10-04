import { beforeEach, describe, expect, it } from 'vitest';

import { readUiPreference, uiScopeForUser, writeUiPreference } from './uiPreferences';
import { spoolViewPreferenceKey } from './spoolViewPreference';

describe('spool view preferences', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('stores plugin and website grid/list choices independently for the same account', () => {
    const scope = uiScopeForUser(42);
    const websiteKey = spoolViewPreferenceKey(false);
    const pluginKey = spoolViewPreferenceKey(true);

    writeUiPreference(scope, websiteKey, 'list');
    writeUiPreference(scope, pluginKey, 'grid');

    expect(readUiPreference(scope, websiteKey)).toBe('list');
    expect(readUiPreference(scope, pluginKey)).toBe('grid');

    writeUiPreference(scope, pluginKey, 'list');

    expect(readUiPreference(scope, websiteKey)).toBe('list');
    expect(readUiPreference(scope, pluginKey)).toBe('list');
  });

});
