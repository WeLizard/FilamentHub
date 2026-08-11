import { describe, expect, it } from 'vitest';
import { formatBytes } from './formatBytes';

describe('formatBytes', () => {
  it('keeps empty attachment sizes empty', () => {
    expect(formatBytes(null, 'en-US')).toBe('');
    expect(formatBytes(undefined, 'en-US')).toBe('');
  });

  it('formats bytes, kilobytes, and megabytes compactly', () => {
    expect(formatBytes(512, 'en-US')).toBe('512 B');
    expect(formatBytes(1536, 'en-US')).toBe('1.5 KB');
    expect(formatBytes(1.5 * 1024 * 1024, 'en-US')).toBe('1.5 MB');
  });

  it('uses the requested locale for decimal separators', () => {
    expect(formatBytes(1536, 'ru-RU')).toBe('1,5 KB');
  });
});
