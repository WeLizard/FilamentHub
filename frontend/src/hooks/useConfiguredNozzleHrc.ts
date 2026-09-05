import { useQuery } from '@tanstack/react-query';
import { printerProfilesAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { usePrinterSelection } from './usePrinterSelection';
import { configuredNozzleHrc } from '../utils/nozzleHardness';

export function useConfiguredNozzleHrc(): number | null {
  const { user } = useAuth();
  const [selection] = usePrinterSelection();

  const { data: profilesList } = useQuery({
    queryKey: ['printer-profiles', 'all-owned', user?.id],
    queryFn: ({ signal }) => printerProfilesAPI.listAllOwned(user!.id, signal),
    enabled: !!user && selection.printerProfileId != null,
  });

  if (selection.printerProfileId == null) {
    return null;
  }

  const profile = profilesList?.find((item) => item.id === selection.printerProfileId);
  return configuredNozzleHrc(profile?.orcaslicer_settings);
}
