import { beforeEach, describe, expect, it } from 'vitest';

import { consumeAuthReturnTo, rememberAuthReturnTo } from './authReturn';

describe('authReturn', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.history.replaceState({}, '', '/brand-invite/test-token?source=email');
  });

  it('restores an invite route once after OAuth', () => {
    rememberAuthReturnTo();

    expect(consumeAuthReturnTo()).toBe('/brand-invite/test-token?source=email');
    expect(consumeAuthReturnTo()).toBeNull();
  });

  it('rejects protocol-relative redirects', () => {
    rememberAuthReturnTo('//evil.example/steal');

    expect(consumeAuthReturnTo()).toBeNull();
  });
});
