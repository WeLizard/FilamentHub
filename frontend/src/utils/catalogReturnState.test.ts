import { describe, expect, it, vi } from 'vitest';

import {
  navigateBackToCatalog,
  parseCatalogSearch,
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
    const parsed = parseCatalogSearch('?auth=register&color=purple-ish&brand=0&printer=1.5&country=USA&x=1');
    expect(parsed.filters).toMatchObject({ color: null, brand: null, printer: null, country: null });
    expect(parsed.canonicalSearch).toBe('auth=register&x=1');
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
