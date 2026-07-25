import { useQuery } from '@tanstack/react-query';
import { printerProfilesAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { usePrinterSelection } from './usePrinterSelection';
import { configuredNozzleHrc } from '../utils/nozzleHardness';

/**
 * Твёрдость сопла в конфигурации, выбранной для рекомендаций. Запрос делит
 * кэш с `PrinterConfigPicker`, поэтому лишней сетевой работы не добавляет.
 * null — конфигурация не выбрана или её сопло неизвестно.
 */
export function useConfiguredNozzleHrc(): number | null {
  const { user } = useAuth();
  const [selection] = usePrinterSelection();

  const { data: profilesList } = useQuery({
    queryKey: ['printer-profiles', 'all-owned', user?.id],
    queryFn: () => printerProfilesAPI.listAllOwned(user!.id),
    enabled: !!user && selection.printerProfileId != null,
  });

  if (selection.printerProfileId == null) {
    return null;
  }

  const profile = profilesList?.find((item) => item.id === selection.printerProfileId);
  return configuredNozzleHrc(profile?.orcaslicer_settings);
}
