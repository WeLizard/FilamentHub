import { describe, expect, it } from 'vitest';
import { filamentHolderMessage, readFilamentSlugHolder } from './filamentDuplicate';

const params = {
  filament_id: 7,
  filament_name: 'ABS',
  brand_name: 'Acme',
  color_name: 'Black',
  inactive: true,
};

describe('readFilamentSlugHolder', () => {
  it('reads an inactive holder so the form can explain it instead of offering a pick', () => {
    const holder = readFilamentSlugHolder({ code: 'ERR_FILAMENT_ALREADY_EXISTS', params });
    expect(holder).toMatchObject({ id: 7, name: 'ABS', brandName: 'Acme', inactive: true });
  });

  it('treats a holder without the inactive flag as selectable', () => {
    const holder = readFilamentSlugHolder({
      code: 'ERR_FILAMENT_ALREADY_EXISTS',
      params: { ...params, inactive: false },
    });
    expect(holder?.inactive).toBe(false);
  });

  it('returns null for a bare code with nothing to point at', () => {
    expect(readFilamentSlugHolder({ code: 'ERR_FILAMENT_ALREADY_EXISTS' })).toBeNull();
    expect(readFilamentSlugHolder('ERR_FILAMENT_ALREADY_EXISTS')).toBeNull();
  });
});

describe('filamentHolderMessage', () => {
  it('names the holder and picks the off-the-shelf wording for inactive ones', () => {
    const t = ((key: string, opts: { name: string }) => `${key}|${opts.name}`) as never;
    const holder = readFilamentSlugHolder({ code: 'ERR_FILAMENT_ALREADY_EXISTS', params })!;
    expect(filamentHolderMessage(t, holder)).toBe(
      'apiErrors.ERR_FILAMENT_ALREADY_EXISTS_INACTIVE|Acme ABS (Black)',
    );
    expect(filamentHolderMessage(t, { ...holder, inactive: false })).toBe(
      'apiErrors.ERR_FILAMENT_ALREADY_EXISTS_NAMED|Acme ABS (Black)',
    );
  });
});
