import { useQuery } from '@tanstack/react-query';

import { authAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

/**
 * The country a reader without an account appears to come from.
 *
 * `useReaderCountry` deliberately knows only the confirmed choice in a profile.
 * A guest has none, so a public brand page starts from this guess and shows a
 * switch next to it. It is asked once per visit and never stored.
 *
 * `ready` is false while the answer is on its way, so the page does not draw
 * the general version first and then replace it.
 */
export function useGuestCountryGuess(): { country: string | undefined; ready: boolean } {
  const { user, isLoading } = useAuth();
  const isGuest = !user && !isLoading;
  const query = useQuery({
    queryKey: ['reader-country-guess'],
    queryFn: authAPI.getReaderCountry,
    enabled: isGuest,
    staleTime: Infinity,
    retry: false,
  });
  if (isLoading) return { country: undefined, ready: false };
  if (!isGuest) return { country: undefined, ready: true };
  return { country: query.data ?? undefined, ready: !query.isPending };
}
