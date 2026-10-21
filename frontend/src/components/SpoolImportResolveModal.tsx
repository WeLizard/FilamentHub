import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { useTranslation } from 'react-i18next';
import { filamentsAPI, spoolsAPI } from '../api/client';
import type { SpoolCompatImportPreview } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { Dropdown } from './Dropdown';
import { ModalOverlay } from './ModalOverlay';

interface SpoolImportResolveModalProps {
  importId: number;
  onClose: () => void;
  onResolved: () => void;
}

const FIELD_LABELS: Record<string, string> = {
  name: 'name',
  brand_name: 'brand',
  material_type: 'materialType',
  color_hex: 'color',
  diameter: 'diameter',
  density: 'density',
  weight: 'weight',
  spool_weight: 'spoolWeight',
  settings_extruder_temp: 'extruderTemp',
  settings_bed_temp: 'bedTemp',
};

export function SpoolImportResolveModal({ importId, onClose, onResolved }: SpoolImportResolveModalProps) {
  const { t } = useTranslation();
  const [selectedFilamentId, setSelectedFilamentId] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [isResolving, setIsResolving] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const detailQuery = useQuery({
    queryKey: ['spool-compat-import', importId],
    queryFn: () => spoolsAPI.getImport(importId),
    retry: false,
  });
  const filamentsQuery = useQuery({
    queryKey: ['spool-compat-import-filaments', debouncedSearch],
    queryFn: () => filamentsAPI.list({ active_only: true, search: debouncedSearch, page: 1, size: 20 }),
    retry: false,
  });
  const previewQuery = useQuery({
    queryKey: ['spool-compat-import-preview', importId, selectedFilamentId, detailQuery.data?.revision],
    queryFn: () => spoolsAPI.previewImportMatch(importId, selectedFilamentId!),
    enabled: selectedFilamentId !== null && detailQuery.data !== undefined && detailQuery.data.resolved_filament_id === null,
    retry: false,
  });

  const selectedFilament = previewQuery.data?.target_filament;
  const options = useMemo(() => {
    const items = filamentsQuery.data?.items ?? [];
    const result = items.map((filament) => ({
      value: filament.id,
      label: [filament.brand_name, filament.name, filament.material_type].filter(Boolean).join(' · '),
    }));
    if (selectedFilament && !result.some((item) => item.value === selectedFilament.id)) {
      result.unshift({
        value: selectedFilament.id,
        label: [selectedFilament.brand_name, selectedFilament.name, selectedFilament.material_type].filter(Boolean).join(' · '),
      });
    }
    return result;
  }, [filamentsQuery.data, selectedFilament]);

  const preview: SpoolCompatImportPreview | undefined = previewQuery.data;
  const reviewedSnapshot = !previewQuery.isFetching && !previewQuery.isError
    && preview?.target_filament.id === selectedFilamentId
    && preview.revision === detailQuery.data?.revision
    ? preview : undefined;
  const canResolve = !isResolving && !detailQuery.isFetching && !previewQuery.isFetching
    && !detailQuery.isError && !previewQuery.isError
    && selectedFilamentId !== null
    && preview?.target_filament.id === selectedFilamentId
    && Boolean(preview.preview_token)
    && preview.revision === detailQuery.data?.revision
    && detailQuery.data.resolved_filament_id === null;

  const messageForError = (error: unknown) => {
    const detail = isAxiosError(error) ? error.response?.data?.detail : undefined;
    return translateApiError(t, detail, t('profilePage.spoolImportResolve.requestFailed'));
  };

  const handleResolve = async () => {
    if (!canResolve || !preview || selectedFilamentId === null) return;
    setIsResolving(true);
    setResolveError(null);
    try {
      await spoolsAPI.resolveImport(importId, selectedFilamentId, preview.revision, preview.preview_token);
      onResolved();
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 409) {
        setConflict(true);
        const refreshed = await detailQuery.refetch();
        if (refreshed.data?.revision === preview.revision) await previewQuery.refetch();
      } else {
        setResolveError(messageForError(error));
      }
    } finally {
      setIsResolving(false);
    }
  };

  const formatValue = (value: string | number | null) => value === null || value === ''
    ? t('profilePage.spoolImportResolve.emptyValue')
    : String(value);

  return (
    <ModalOverlay onClose={onClose}>
      <div role="dialog" aria-label={t('profilePage.spoolImportResolve.title')} className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/20 bg-gray-900 p-5 text-white sm:p-7">
        <h2 className="text-xl font-semibold">{t('profilePage.spoolImportResolve.title')}</h2>
        <p className="mt-2 text-sm text-gray-300">{t('profilePage.spoolImportResolve.intro')}</p>

        {detailQuery.isPending && <p className="mt-5 text-sm text-gray-300">{t('profilePage.spoolImportResolve.loading')}</p>}
        {detailQuery.isError && (
          <div className="mt-5 text-sm text-red-300">
            <p role="alert">{messageForError(detailQuery.error)}</p>
            <button type="button" onClick={() => detailQuery.refetch()} className="mt-2 rounded-lg border border-white/20 px-3 py-2">{t('profilePage.spoolImportResolve.retry')}</button>
          </div>
        )}

        {detailQuery.data && (
          <div className="mt-5 space-y-5">
            <div className="rounded-xl border border-white/10 bg-white/5 p-4">
              <h3 className="font-medium">{t('profilePage.spoolImportResolve.importedMaterial')}</h3>
              <p className="mt-1 text-sm text-gray-200">{[(reviewedSnapshot ?? detailQuery.data).material.brand_name, (reviewedSnapshot ?? detailQuery.data).material.name, (reviewedSnapshot ?? detailQuery.data).material.material_type].filter(Boolean).join(' · ') || t('profilePage.spoolNoFilament')}</p>
              <p className="mt-1 text-xs text-gray-400">{t('profilePage.spoolImportResolve.source', { source: (reviewedSnapshot ?? detailQuery.data).source })}</p>
              <dl className="mt-3 grid gap-x-5 gap-y-2 text-xs sm:grid-cols-2">
                {Object.entries((reviewedSnapshot ?? detailQuery.data).material).filter(([, value]) => value !== null).map(([field, value]) => (
                  <div key={field} className="flex gap-2">
                    <dt className="text-gray-400">{FIELD_LABELS[field] ? t(`profilePage.spoolImportResolve.fields.${FIELD_LABELS[field]}`) : field}:</dt>
                    <dd className="break-all text-gray-200">{String(value)}</dd>
                  </div>
                ))}
              </dl>
            </div>

            <div>
              <h3 className="mb-2 font-medium">{t('profilePage.spoolImportResolve.affectedSpools', { count: (reviewedSnapshot ?? detailQuery.data).spools.length })}</h3>
              <ul className="max-h-32 overflow-y-auto rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-gray-300">
                {(reviewedSnapshot ?? detailQuery.data).spools.map((spool) => <li key={spool.id}>#{spool.id} · {spool.name}</li>)}
              </ul>
            </div>

            {detailQuery.data.resolved_filament_id !== null ? (
              <p role="status" className="text-sm text-green-300">{t('profilePage.spoolImportResolve.alreadyResolved')}</p>
            ) : (
              <>
                <Dropdown
                  label={t('profilePage.spoolImportResolve.chooseFilament')}
                  value={selectedFilamentId ?? ''}
                  options={options}
                  onChange={(value) => {
                    setSelectedFilamentId(typeof value === 'number' ? value : null);
                    setConflict(false);
                    setResolveError(null);
                  }}
                  filterable
                  filterValue={search}
                  onFilterChange={setSearch}
                  placeholder={t('profilePage.spoolImportResolve.searchFilament')}
                  emptyMessage={filamentsQuery.isFetching ? t('profilePage.spoolImportResolve.loading') : t('profilePage.spoolImportResolve.noMatches')}
                />
                {filamentsQuery.isError && <p role="alert" className="mt-2 text-sm text-red-300">{messageForError(filamentsQuery.error)}</p>}

                {previewQuery.isFetching && <p className="text-sm text-gray-300">{t('profilePage.spoolImportResolve.loadingPreview')}</p>}
                {previewQuery.isError && (
                  <div className="text-sm text-red-300">
                    <p role="alert">{messageForError(previewQuery.error)}</p>
                    <button type="button" onClick={() => previewQuery.refetch()} className="mt-2 rounded-lg border border-white/20 px-3 py-2">{t('profilePage.spoolImportResolve.retry')}</button>
                  </div>
                )}
                {conflict && <p role="alert" className="text-sm text-amber-200">{t('profilePage.spoolImportResolve.conflict')}</p>}
                {reviewedSnapshot && (
                  <div>
                    <h3 className="font-medium">{t('profilePage.spoolImportResolve.differences')}</h3>
                    {reviewedSnapshot.differences.length === 0 ? (
                      <p className="mt-2 text-sm text-gray-300">{t('profilePage.spoolImportResolve.noDifferences')}</p>
                    ) : (
                      <div className="mt-2 overflow-x-auto rounded-xl border border-white/10">
                        <table className="w-full text-left text-sm">
                          <thead className="bg-white/5 text-gray-300"><tr>
                            <th className="px-3 py-2">{t('profilePage.spoolImportResolve.field')}</th>
                            <th className="px-3 py-2">{t('profilePage.spoolImportResolve.imported')}</th>
                            <th className="px-3 py-2">{t('profilePage.spoolImportResolve.catalog')}</th>
                          </tr></thead>
                          <tbody>{reviewedSnapshot.differences.map((difference) => (
                            <tr key={difference.field} className="border-t border-white/10">
                              <td className="px-3 py-2 text-gray-300">{FIELD_LABELS[difference.field] ? t(`profilePage.spoolImportResolve.fields.${FIELD_LABELS[difference.field]}`) : difference.field}</td>
                              <td className="px-3 py-2">{formatValue(difference.imported)}</td>
                              <td className="px-3 py-2">{formatValue(difference.catalog)}</td>
                            </tr>
                          ))}</tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
                {resolveError && <p role="alert" className="text-sm text-red-300">{resolveError}</p>}
              </>
            )}
          </div>
        )}

        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button type="button" onClick={onClose} className="rounded-lg border border-white/20 px-4 py-2 text-sm text-gray-200 hover:bg-white/10">{t('common.cancel')}</button>
          {detailQuery.data?.resolved_filament_id === null && (
            <button type="button" onClick={handleResolve} disabled={!canResolve} className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-50">{t('profilePage.spoolImportResolve.confirm')}</button>
          )}
        </div>
      </div>
    </ModalOverlay>
  );
}
