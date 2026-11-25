import { describe, expect, it } from 'vitest';

import { GENERAL_MARKET, brandMarketCountry, parseMarketChoice } from './brandMarket';

describe('brand market', () => {
  it('puts the reader\'s own choice above the profile and the guess', () => {
    expect(brandMarketCountry({ choice: 'CN', profileCountry: 'RU', guessedCountry: 'DE' })).toBe('CN');
    expect(brandMarketCountry({ choice: null, profileCountry: 'RU', guessedCountry: 'DE' })).toBe('RU');
    expect(brandMarketCountry({ choice: null, profileCountry: undefined, guessedCountry: 'DE' })).toBe('DE');
  });

  it('lets a reader leave a guessed country for the general page', () => {
    // Without this a guest whose connection is misread could never see the general links.
    expect(brandMarketCountry({ choice: GENERAL_MARKET, profileCountry: 'RU', guessedCountry: 'DE' }))
      .toBeUndefined();
  });

  it('reads only a country or the general page from the address', () => {
    expect(parseMarketChoice('cn')).toBe('CN');
    expect(parseMarketChoice('General')).toBe(GENERAL_MARKET);
    expect(parseMarketChoice('china')).toBeNull();
    expect(parseMarketChoice(null)).toBeNull();
  });
});
