import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { authAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import {
  currencySymbol,
  defaultCurrencyForLanguage,
  normalizeCurrency,
} from '../utils/currency';

export const USER_PREFERENCES_QUERY_KEY = ['user-preferences'] as const;

export function useUserCurrency() {
  const { i18n } = useTranslation();
  const { isAuthenticated } = useAuth();
  const query = useQuery({
    queryKey: USER_PREFERENCES_QUERY_KEY,
    queryFn: authAPI.getPreferences,
    enabled: isAuthenticated,
    staleTime: 300_000,
  });
  const currency = normalizeCurrency(
    query.data?.currency || defaultCurrencyForLanguage(i18n.language),
  );

  return {
    currency,
    symbol: currencySymbol(currency),
    isLoading: query.isLoading,
  };
}
