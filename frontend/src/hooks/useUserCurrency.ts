import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { authAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useReaderCountry } from './useReaderCountry';
import {
  currencySymbol,
  defaultCurrencyForCountry,
  normalizeCurrency,
} from '../utils/currency';

export const USER_PREFERENCES_QUERY_KEY = ['user-preferences'] as const;

/**
 * Валюта человека: сначала выбранная им, затем деньги его страны, и только
 * потом язык интерфейса.
 *
 * Язык не является юрисдикцией: русскоязычный человек в Германии платит в евро,
 * и подставлять ему рубли лишь потому, что сайт у него на русском, неверно.
 * Язык остаётся догадкой на то время, пока страна неизвестна.
 */
export function useUserCurrency() {
  const { i18n } = useTranslation();
  const { isAuthenticated } = useAuth();
  const country = useReaderCountry();
  const query = useQuery({
    queryKey: USER_PREFERENCES_QUERY_KEY,
    queryFn: authAPI.getPreferences,
    enabled: isAuthenticated,
    staleTime: 300_000,
  });
  const currency = normalizeCurrency(
    query.data?.currency || defaultCurrencyForCountry(country, i18n.language),
  );

  return {
    currency,
    symbol: currencySymbol(currency),
    isLoading: query.isLoading,
  };
}
