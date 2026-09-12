import { describe, expect, it, vi } from 'vitest';

import {
  consumeCatalogReturn,
  navigateBackToCatalog,
  parseCatalogSearch,
  recordCatalogReturn,
  updateCatalogSearch,
} from './catalogReturnState';

describe('catalog return state', () => {
  it('hydrates valid filters and canonicalizes only owned parameters', () => {
    const parsed = parseCatalogSearch(
      '?auth=login&q=PLA&material=PETG&color=red&brand=3&printer=7&country=de&future=kept',
    );

    expect(parsed.filters).toEqual({
      q: 'PLA', material: 'PETG', color: 'red', brand: 3, printer: 7, country: 'DE',
    });
    expect(new URLSearchParams(parsed.canonicalSearch)).toEqual(
      new URLSearchParams('auth=login&q=PLA&material=PETG&color=red&brand=3&printer=7&country=DE&future=kept'),
    );
  });

  it('drops malformed catalog filters while preserving unrelated parameters', () => {
    const parsed = parseCatalogSearch('?auth=register&color=purple-ish&brand=0&printer=1.5&country=ZZ&x=1');
    expect(parsed.filters).toMatchObject({ color: null, brand: null, printer: null, country: null });
    expect(parsed.canonicalSearch).toBe('auth=register&x=1');
  });

  it('consumes a matching return marker once and preserves router history state', () => {
    window.history.replaceState({ idx: 4, key: 'router-key', usr: { kept: true } }, document.title);
    const marker = {
      version: 1 as const,
      entryKey: 'entry-1',
      catalogUrl: '/?q=PLA',
      anchorId: 'catalog-filament-7',
      scrollY: 320,
      anchorOffset: -40,
    };
    recordCatalogReturn(marker);

    expect(consumeCatalogReturn(marker)).toBe(true);
    expect(consumeCatalogReturn(marker)).toBe(false);
    expect(window.history.state).toEqual({ idx: 4, key: 'router-key', usr: { kept: true } });
  });

  it('updates one filter without losing auth or future parameters', () => {
    expect(updateCatalogSearch('?auth=login&x=1&q=old', 'q', 'new')).toBe('auth=login&x=1&q=new');
  });

  it('uses browser back only for a validated catalog origin', () => {
    const navigate = vi.fn();
    navigateBackToCatalog(navigate, { from: 'catalog', catalogEntryKey: 'entry-1' });
    navigateBackToCatalog(navigate, { from: 'catalog' });
    expect(navigate.mock.calls).toEqual([[-1], ['/']]);
  });
});
