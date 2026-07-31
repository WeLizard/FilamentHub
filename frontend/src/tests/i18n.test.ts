import { afterEach, describe, expect, it, vi } from 'vitest';

describe('embedded catalog language', () => {
  afterEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, '', '/');
    vi.resetModules();
  });

  it('lets the OrcaSlicer lng query override a saved browser language', async () => {
    window.localStorage.setItem('i18nextLng', 'en');
    window.history.replaceState({}, '', '/embed/catalog?lng=ru');

    const { default: i18n } = await import('../i18n');

    expect(i18n.resolvedLanguage).toBe('ru');
    expect(document.documentElement.lang).toBe('ru');
  });
});
