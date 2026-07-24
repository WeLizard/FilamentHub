/** Add a printer by hand, picking its model from the catalog.
 *
 *  Network discovery only sees machines whose slicer preset carries a host
 *  address, which Bambu presets never do — they bind through OrcaSlicer's own
 *  device manager. Without this route those owners cannot register a printer at
 *  all, so this is the one path that works for every machine. */

import { useState, FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Loader2, Plus, X } from 'lucide-react';
import type { AxiosError } from 'axios';
import { physicalPrintersAPI, printersAPI } from '../api/client';
import { useDebounce } from '../hooks/useDebounce';
import { ModalOverlay } from './ModalOverlay';
import { Dropdown } from './Dropdown';
import { translateApiError } from '../utils/translateApiError';

interface AddPhysicalPrinterModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Attach these configurations to the new printer (create-from-configuration). */
  initialProfileIds?: number[];
  /** Prefill when the printer is being created out of a known configuration. */
  initialName?: string;
  initialPrinterId?: number | null;
}

export function AddPhysicalPrinterModal({
  isOpen,
  onClose,
  initialProfileIds = [],
  initialName = '',
  initialPrinterId = null,
}: AddPhysicalPrinterModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [name, setName] = useState(initialName);
  // Dropdown carries a plain value, so 0 stands for "model not chosen".
  const [printerId, setPrinterId] = useState<number>(initialPrinterId ?? 0);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const debouncedSearch = useDebounce(search, 250);

  // Machines already installed in the person's OrcaSlicer: the fastest way in,
  // and the only practical one for a Bambu, which discovery cannot see.
  const { data: candidates } = useQuery({
    queryKey: ['printer-candidates'],
    queryFn: physicalPrintersAPI.listInstalledCandidates,
    enabled: isOpen && initialProfileIds.length === 0,
  });

  const { data: catalogList } = useQuery({
    queryKey: ['printers', 'add-printer-picker', debouncedSearch],
    queryFn: () =>
      printersAPI.list({
        page: 1,
        size: 50,
        active_only: true,
        search: debouncedSearch.trim() || undefined,
      }),
    enabled: isOpen,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      physicalPrintersAPI.create({
        name: name.trim(),
        printer_id: printerId || null,
        printer_profile_ids: initialProfileIds,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
      setError(null);
      onClose();
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setError(translateApiError(t, err.response?.data?.detail, t('addPrinter.error')));
    },
  });

  if (!isOpen) return null;

  const nameInvalid = name.trim().length === 0;
  const modelOptions = (catalogList?.items ?? []).map((p) => ({ value: p.id, label: p.name }));

  return (
    <ModalOverlay onClose={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-white/20 bg-gray-900">
        <form
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            if (!nameInvalid) createMutation.mutate();
          }}
        >
          <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
            <h2 className="text-lg font-semibold text-white">{t('addPrinter.title')}</h2>
            <button
              type="button"
              onClick={onClose}
              className="text-gray-400 transition-colors hover:text-white"
              aria-label={t('common.close')}
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="space-y-4 px-6 py-5">
            <p className="text-xs text-gray-400">{t('addPrinter.description')}</p>

            {(candidates?.length ?? 0) > 0 && (
              <div>
                <span className="text-sm text-gray-300">{t('addPrinter.foundInOrca')}</span>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {candidates!.map((candidate) => (
                    <button
                      key={candidate.model}
                      type="button"
                      onClick={() => {
                        setName(candidate.model);
                        setPrinterId(candidate.printer_id ?? 0);
                      }}
                      className="rounded-full border border-purple-400/30 bg-purple-500/15 px-2.5 py-1 text-xs text-purple-100 transition-colors hover:bg-purple-500/25"
                    >
                      {candidate.model}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <label className="block">
              <span className="text-sm text-gray-300">{t('addPrinter.name')}</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('addPrinter.namePlaceholder')}
                className="mt-1 w-full rounded-lg border border-white/20 bg-white/10 px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                autoFocus
              />
            </label>

            <div>
              <span className="text-sm text-gray-300">{t('addPrinter.model')}</span>
              <div className="mt-1">
                <Dropdown
                  value={printerId}
                  onChange={(value) => setPrinterId(Number(value))}
                  options={modelOptions}
                  placeholder={t('addPrinter.modelPlaceholder')}
                  filterable
                  filterValue={search}
                  onFilterChange={setSearch}
                  emptyMessage={t('addPrinter.modelEmpty')}
                />
              </div>
              <p className="mt-1 text-[11px] text-gray-500">{t('addPrinter.modelHint')}</p>
            </div>

            {error && <p className="text-sm text-rose-400">{error}</p>}
          </div>

          <div className="flex justify-end gap-3 border-t border-white/10 px-6 py-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-white/20 px-4 py-2 text-sm text-gray-200 transition-colors hover:bg-white/10"
            >
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              disabled={nameInvalid || createMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm text-white transition-colors hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {createMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              {t('addPrinter.submit')}
            </button>
          </div>
        </form>
      </div>
    </ModalOverlay>
  );
}
