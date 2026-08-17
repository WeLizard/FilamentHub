import { useQuery } from '@tanstack/react-query';

import { currenciesAPI } from '../api/client';
import { setCurrencyCatalogue } from '../utils/currency';

/**
 * Loads the currency reference once per session and hands it to the module helpers
 * that format money outside React. Mounted at the application root so the re-render
 * on arrival reaches every list and price on the page.
 */
export function useCurrencyCatalogue(): void {
  useQuery({
    queryKey: ['currencies'],
    queryFn: async () => {
      const rows = await currenciesAPI.list();
      setCurrencyCatalogue(rows);
      return rows;
    },
    staleTime: 24 * 60 * 60 * 1000,
    retry: 1,
  });
}
