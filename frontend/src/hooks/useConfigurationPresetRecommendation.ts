import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import {
  physicalPrintersAPI,
  presetsAPI,
  printerProfilesAPI,
} from '../api/client';
import type { RecommendedPresetItem } from '../types/api';
import {
  type PrinterSelection,
  usePrinterSelection,
} from './usePrinterSelection';

export interface PrinterConfigurationOption extends PrinterSelection {
  key: string;
  label: string;
}

interface ConfigurationPresetRecommendation {
  options: PrinterConfigurationOption[];
  selectedKey: string;
  select: (key: string) => void;
  recommendation: RecommendedPresetItem | null;
  printerName: string | null;
  isLoadingOptions: boolean;
  isOptionsError: boolean;
  isLoadingRecommendation: boolean;
  isRecommendationError: boolean;
}

const sameSelection = (left: PrinterSelection, right: PrinterSelection) =>
  left.physicalPrinterId === right.physicalPrinterId
  && left.printerProfileId === right.printerProfileId;

export function useConfigurationPresetRecommendation(
  userId: number | null,
  filamentId: number | null,
): ConfigurationPresetRecommendation {
  const [storedSelection, persistSelection] = usePrinterSelection();
  const [selection, setSelection] = useState<PrinterSelection>(storedSelection);

  useEffect(() => {
    setSelection((current) => (
      sameSelection(current, storedSelection) ? current : storedSelection
    ));
  }, [storedSelection.physicalPrinterId, storedSelection.printerProfileId]);

  const printersQuery = useQuery({
    queryKey: ['physical-printers'],
    queryFn: physicalPrintersAPI.list,
    enabled: userId !== null,
    staleTime: 30_000,
  });
  const profilesQuery = useQuery({
    queryKey: ['printer-profiles', 'all-owned', userId],
    queryFn: () => printerProfilesAPI.listAllOwned(userId!),
    enabled: userId !== null,
    staleTime: 30_000,
  });

  const options = useMemo(() => {
    const profiles = (profilesQuery.data ?? []).filter(
      (profile) => profile.active && profile.printer_id !== null,
    );
    const profileById = new Map(profiles.map((profile) => [profile.id, profile]));
    const linkedProfileIds = new Set<number>();
    const linked: PrinterConfigurationOption[] = [];

    for (const printer of printersQuery.data ?? []) {
      for (const profileId of printer.printer_profile_ids) {
        const profile = profileById.get(profileId);
        if (!profile) continue;
        linkedProfileIds.add(profile.id);
        linked.push({
          key: `${printer.id}:${profile.id}`,
          physicalPrinterId: printer.id,
          printerProfileId: profile.id,
          label: `${printer.name} · ${profile.name}`,
        });
      }
    }

    const unbound = profiles
      .filter((profile) => !linkedProfileIds.has(profile.id))
      .map((profile) => ({
        key: `configuration:${profile.id}`,
        physicalPrinterId: null,
        printerProfileId: profile.id,
        label: profile.name,
      }));

    return [...linked, ...unbound].sort((left, right) =>
      left.label.localeCompare(right.label),
    );
  }, [printersQuery.data, profilesQuery.data]);

  const selectedOption = options.find((option) => sameSelection(option, selection));
  const selectedKey = selectedOption?.key ?? '';

  const select = (key: string) => {
    const option = options.find((candidate) => candidate.key === key);
    const next: PrinterSelection = option
      ? {
          physicalPrinterId: option.physicalPrinterId,
          printerProfileId: option.printerProfileId,
        }
      : { physicalPrinterId: null, printerProfileId: null };
    setSelection(next);
    persistSelection(next);
  };

  const recommendationQuery = useQuery({
    queryKey: [
      'recommended-for-configuration',
      selection.physicalPrinterId,
      selection.printerProfileId,
      filamentId,
    ],
    queryFn: () => presetsAPI.getRecommendedForConfiguration({
      physical_printer_id: selection.physicalPrinterId,
      printer_profile_id: selection.printerProfileId!,
      filament_id: filamentId!,
      limit: 20,
    }),
    enabled: userId !== null && selection.printerProfileId !== null && filamentId !== null,
    staleTime: 30_000,
  });

  return {
    options,
    selectedKey,
    select,
    recommendation: recommendationQuery.data?.items[0] ?? null,
    printerName: recommendationQuery.data?.printer_name ?? null,
    isLoadingOptions: printersQuery.isLoading || profilesQuery.isLoading,
    isOptionsError: printersQuery.isError || profilesQuery.isError,
    isLoadingRecommendation: recommendationQuery.isLoading,
    isRecommendationError: recommendationQuery.isError,
  };
}
