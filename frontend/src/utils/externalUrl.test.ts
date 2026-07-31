import { describe, expect, it } from 'vitest';

import { externalUrl, externalUrlHost } from './externalUrl';

describe('externalUrl', () => {
  it('sends a bare domain outside the site instead of into a route', () => {
    // Without a scheme the browser resolves this against the current page, so a
    // brand's site turned into /brands/example.com.
    expect(externalUrl('example.com')).toBe('https://example.com/');
    expect(externalUrl('www.example.com/shop')).toBe('https://www.example.com/shop');
    expect(externalUrl('//example.com')).toBe('https://example.com/');
  });

  it('leaves an address that already says where it goes', () => {
    expect(externalUrl('https://example.com/a?b=c')).toBe('https://example.com/a?b=c');
    expect(externalUrl('http://example.com/')).toBe('http://example.com/');
  });

  it('drops anything that is not a web address', () => {
    // Brand owners edit these fields, so a script here would run for every
    // visitor who clicks it.
    expect(externalUrl('javascript:alert(1)')).toBeNull();
    expect(externalUrl('data:text/html,<script>alert(1)</script>')).toBeNull();
    expect(externalUrl('mailto:someone@example.com')).toBeNull();
    expect(externalUrl('   ')).toBeNull();
    expect(externalUrl(null)).toBeNull();
    expect(externalUrl(undefined)).toBeNull();
  });

  it('shows a readable host and keeps the raw text when it cannot', () => {
    expect(externalUrlHost('www.example.com')).toBe('example.com');
    expect(externalUrlHost('https://shop.example.com/x')).toBe('shop.example.com');
    expect(externalUrlHost('javascript:alert(1)')).toBe('javascript:alert(1)');
  });
});
