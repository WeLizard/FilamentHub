/**
 * Which country's version of a brand page to show.
 *
 * A brand can keep its own description, links and shops for a country. The
 * reader's own choice on the page comes first, then the country in their
 * profile, then, for a reader without an account, the country their
 * connection appears to come from. That last one is only a first guess: the
 * page says which country is shown and lets the reader change it.
 */

/** The choice "show the brand's general page", as it appears in the address. */
export const GENERAL_MARKET = 'general';

export type MarketChoice = typeof GENERAL_MARKET | string | null;

/** The `country` value of a brand page address: a country, "general", or no choice. */
export function parseMarketChoice(value: string | null): MarketChoice {
  if (value === null) return null;
  if (value.toLowerCase() === GENERAL_MARKET) return GENERAL_MARKET;
  return /^[A-Za-z]{2}$/.test(value) ? value.toUpperCase() : null;
}

export function brandMarketCountry({
  choice,
  profileCountry,
  guessedCountry,
}: {
  choice: MarketChoice;
  profileCountry: string | undefined;
  guessedCountry: string | undefined;
}): string | undefined {
  if (choice === GENERAL_MARKET) return undefined;
  return choice ?? profileCountry ?? guessedCountry;
}
