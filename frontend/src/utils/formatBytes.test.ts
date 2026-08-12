import { describe, expect, it } from 'vitest';
import { formatBytes } from './formatBytes';

describe('formatBytes', () => {
  it('keeps empty attachment sizes empty', () => {
    expect(formatBytes(null, 'en-US')).toBe('');
    expect(formatBytes(undefined, 'en-US')).toBe('');
    expect(formatBytes(Number.NaN, 'en-US')).toBe('');
    expect(formatBytes(-1, 'en-US')).toBe('');
  });

  it('formats bytes through gigabytes compactly', () => {
    expect(formatBytes(512, 'en-US')).toBe('512 B');
    expect(formatBytes(1536, 'en-US')).toBe('1.5 KB');
    expect(formatBytes(1.5 * 1024 * 1024, 'en-US')).toBe('1.5 MB');
    expect(formatBytes(1.5 * 1024 * 1024 * 1024, 'en-US')).toBe('1.5 GB');
  });

  it('uses the requested locale for decimal separators', () => {
    expect(formatBytes(1536, 'ru-RU')).toBe('1,5 KB');
  });
});
