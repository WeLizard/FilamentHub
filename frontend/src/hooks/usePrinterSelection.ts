import { useMutation, useQueryClient } from '@tanstack/react-query';
import { authAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

/**
 * The catalog "recommend for my printer" selection. Identity is the
 * configuration (printerProfileId); physicalPrinterId is optional context that
 * lets the backend verify the printer↔configuration link.
 *
 * Stored on the account (not the browser) so it follows the user across
 * devices; the server FK clears it automatically when the printer/config is
 * deleted, so a stale choice cannot linger or leak between accounts.
 */
export interface PrinterSelection {
  physicalPrinterId: number | null;
  printerProfileId: number | null;
}

export function usePrinterSelection(): [PrinterSelection, (value: PrinterSelection) => void] {
  const { user, refreshUser } = useAuth();
  const queryClient = useQueryClient();

  const selection: PrinterSelection = {
    physicalPrinterId: user?.recommend_physical_printer_id ?? null,
    printerProfileId: user?.recommend_printer_profile_id ?? null,
  };

  const mutation = useMutation({
    mutationFn: (value: PrinterSelection) =>
      authAPI.updateProfile({
        recommend_physical_printer_id: value.physicalPrinterId,
        recommend_printer_profile_id: value.printerProfileId,
      }),
    onSuccess: () => {
      refreshUser();
      queryClient.invalidateQueries({ queryKey: ['recommended-for-configuration'] });
    },
  });

  const setSelection = (value: PrinterSelection) => mutation.mutate(value);

  return [selection, setSelection];
}
