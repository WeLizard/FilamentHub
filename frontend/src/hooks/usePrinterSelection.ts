import { useCallback, useState } from 'react';

/**
 * The catalog "recommend for my printer" selection. Identity is the
 * configuration (printerProfileId); physicalPrinterId is optional context that
 * lets the backend verify the printer↔configuration link. Kept in localStorage,
 * never on the user account.
 */
export interface PrinterSelection {
  physicalPrinterId: number | null;
  printerProfileId: number | null;
}

const KEY = 'fh.catalog.printerSelection';
const EMPTY: PrinterSelection = { physicalPrinterId: null, printerProfileId: null };

function read(): PrinterSelection {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as Partial<PrinterSelection>;
    return {
      physicalPrinterId:
        typeof parsed.physicalPrinterId === 'number' ? parsed.physicalPrinterId : null,
      printerProfileId:
        typeof parsed.printerProfileId === 'number' ? parsed.printerProfileId : null,
    };
  } catch {
    return EMPTY;
  }
}

export function usePrinterSelection(): [PrinterSelection, (value: PrinterSelection) => void] {
  const [selection, setSelectionState] = useState<PrinterSelection>(read);

  const setSelection = useCallback((value: PrinterSelection) => {
    setSelectionState(value);
    try {
      localStorage.setItem(KEY, JSON.stringify(value));
    } catch {
      /* storage unavailable — selection stays in-memory for this session */
    }
  }, []);

  return [selection, setSelection];
}
