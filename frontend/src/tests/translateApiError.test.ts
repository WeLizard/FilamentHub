import { describe, it, expect, vi } from 'vitest';
import { translateApiError } from '../utils/translateApiError';
import type { TFunction } from 'i18next';

/** Create a mock t() that looks up keys from a flat dictionary. */
function createMockT(translations: Record<string, string> = {}): TFunction {
  return ((key: string, params?: Record<string, unknown>) => {
    const val = translations[key];
    if (!val) return key; // i18next returns key when missing
    if (!params) return val;
    // Simple interpolation: {{param}}
    return val.replace(/\{\{(\w+)\}\}/g, (_, k) => String(params[k] ?? `{{${k}}}`));
  }) as unknown as TFunction;
}

const defaultTranslations: Record<string, string> = {
  'apiErrors.UNKNOWN_ERROR': 'Unknown error',
  'apiErrors.ERR_USER_NOT_FOUND': 'User not found',
  'apiErrors.ERR_FIELD_TOO_SHORT': 'Field "{{field_name}}" is too short (min {{min_length}})',
  'apiErrors.ERR_ACCESS_DENIED': 'Access denied',
  'fieldNames.username': 'Username',
};

describe('translateApiError', () => {
  const t = createMockT(defaultTranslations);

  describe('null / undefined', () => {
    it('returns fallback when detail is null', () => {
      expect(translateApiError(t, null, 'my fallback')).toBe('my fallback');
    });

    it('returns UNKNOWN_ERROR when null and no fallback', () => {
      expect(translateApiError(t, null)).toBe('Unknown error');
    });

    it('returns UNKNOWN_ERROR for undefined', () => {
      expect(translateApiError(t, undefined)).toBe('Unknown error');
    });
  });

  describe('structured error { code, params }', () => {
    it('translates code without params', () => {
      expect(translateApiError(t, { code: 'ERR_USER_NOT_FOUND' })).toBe('User not found');
    });

    it('translates code with params', () => {
      const result = translateApiError(t, {
        code: 'ERR_FIELD_TOO_SHORT',
        params: { field_name: 'username', min_length: 3 },
      });
      expect(result).toBe('Field "Username" is too short (min 3)');
    });

    it('falls back to code when translation missing', () => {
      expect(translateApiError(t, { code: 'ERR_UNKNOWN_CODE_XYZ' })).toBe('ERR_UNKNOWN_CODE_XYZ');
    });

    it('uses provided fallback when translation missing', () => {
      expect(translateApiError(t, { code: 'ERR_UNKNOWN_CODE_XYZ' }, 'custom')).toBe('custom');
    });
  });

  describe('string error', () => {
    it('translates ERR_ prefixed string', () => {
      expect(translateApiError(t, 'ERR_ACCESS_DENIED')).toBe('Access denied');
    });

    it('returns ERR_ code as-is when no translation', () => {
      expect(translateApiError(t, 'ERR_SOMETHING_NEW')).toBe('ERR_SOMETHING_NEW');
    });

    it('returns legacy Russian text as-is', () => {
      expect(translateApiError(t, 'Пользователь не найден')).toBe('Пользователь не найден');
    });
  });

  describe('pydantic validation array', () => {
    it('extracts msg from first validation error', () => {
      const detail = [
        { loc: ['body', 'email'], msg: 'Invalid email format', type: 'value_error' },
        { loc: ['body', 'name'], msg: 'Required', type: 'missing' },
      ];
      expect(translateApiError(t, detail)).toBe('Invalid email format');
    });

    it('returns fallback for empty array', () => {
      expect(translateApiError(t, [], 'fallback')).toBe('fallback');
    });
  });

  describe('unexpected types', () => {
    it('returns UNKNOWN_ERROR for number', () => {
      expect(translateApiError(t, 42)).toBe('Unknown error');
    });

    it('returns UNKNOWN_ERROR for boolean', () => {
      expect(translateApiError(t, true)).toBe('Unknown error');
    });
  });
});
