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

  it('uses an explicit locale path before query and saved preferences', async () => {
    window.localStorage.setItem('i18nextLng', 'ru');
    window.history.replaceState({}, '', '/zh/wiki?lng=en');

    const { default: i18n } = await import('../i18n');

    expect(i18n.resolvedLanguage).toBe('zh');
    expect(document.documentElement.lang).toBe('zh');
  });
});
