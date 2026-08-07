import { afterEach, describe, expect, it } from 'vitest';
import i18n from '../i18n';
import { formatDate, formatDateTime } from './formatDate';

const MOMENT = '2026-03-14T15:54:09.944084Z';

afterEach(async () => {
  await i18n.changeLanguage('ru');
});

describe('formatDate', () => {
  it('follows the interface language rather than one chosen for everyone', async () => {
    await i18n.changeLanguage('ru');
    const russian = formatDate(MOMENT);

    await i18n.changeLanguage('zh');
    const chinese = formatDate(MOMENT);

    expect(russian).not.toBe(chinese);
    expect(russian).toContain('2026');
    expect(chinese).toContain('2026');
  });

  it('shows the moment in the reader own zone, so no setting is needed', () => {
    // Один и тот же миг в разных поясах — это разные часы и порой разные сутки.
    const inMoscow = formatDateTime(MOMENT, { timeZone: 'Europe/Moscow', timeStyle: 'short', dateStyle: 'short' });
    const inVladivostok = formatDateTime(MOMENT, { timeZone: 'Asia/Vladivostok', timeStyle: 'short', dateStyle: 'short' });

    expect(inMoscow).not.toBe(inVladivostok);
  });

  it('says nothing when there is nothing to say', () => {
    expect(formatDate(null)).toBe('');
    expect(formatDate(undefined)).toBe('');
    expect(formatDate('')).toBe('');
    expect(formatDate('not a date at all')).toBe('');
    expect(formatDateTime(null)).toBe('');
  });
});
