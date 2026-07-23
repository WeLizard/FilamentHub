import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import { physicalPrintersAPI, printerProfilesAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { Dropdown } from './Dropdown';
import { configLabel } from '../utils/printerConfig';
import type { PrinterSelection } from '../hooks/usePrinterSelection';

interface PrinterConfigPickerProps {
  value: PrinterSelection;
  onChange: (value: PrinterSelection) => void;
}

/**
 * Catalog "recommend for my printer" selector. With physical printers it is a
 * printer→configuration pair; without them it falls back to the user's unbound
 * Orca configurations. The backend resolves the catalog model from the chosen
 * configuration — this component never derives it.
 */
export const PrinterConfigPicker: React.FC<PrinterConfigPickerProps> = ({ value, onChange }) => {
  const { t } = useTranslation();
  const { user } = useAuth();

  const { data: printers } = useQuery({
    queryKey: ['physical-printers'],
    queryFn: physicalPrintersAPI.list,
    enabled: !!user,
  });
  const { data: profilesList } = useQuery({
    queryKey: ['printer-profiles', 'all-owned', user?.id],
    queryFn: () => printerProfilesAPI.listAllOwned(user!.id),
    enabled: !!user,
  });

  const configs = useMemo(
    () => (profilesList ?? []).filter((p) => p.printer_id != null),
    [profilesList],
  );
  const configById = useMemo(() => new Map(configs.map((c) => [c.id, c])), [configs]);

  const physicalPrinters = printers ?? [];
  const hasPhysical = physicalPrinters.length > 0;

  const configOptionsFor = (profileIds: number[]) =>
    profileIds
      .filter((id) => configById.has(id))
      .map((id) => ({ value: id, label: configLabel(configById.get(id)!, t) }));

  if (!user || (configs.length === 0 && !hasPhysical)) return null;

  const selectedPrinter = physicalPrinters.find((p) => p.id === value.physicalPrinterId) ?? null;

  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-2">
      <span className="flex items-center gap-1.5 text-xs text-gray-400 flex-shrink-0">
        <Sparkles className="w-4 h-4 text-purple-300" />
        {t('printerConfig.pickLabel')}
      </span>
      <div className="flex flex-col sm:flex-row gap-2">
        {hasPhysical ? (
          <>
            <Dropdown
              size="sm"
              value={value.physicalPrinterId ?? ''}
              options={physicalPrinters.map((p) => ({ value: p.id, label: p.name }))}
              placeholder={t('printerConfig.selectPrinter')}
              onChange={(val) => {
                const pid = val === '' ? null : Number(val);
                const printer = physicalPrinters.find((p) => p.id === pid);
                const options = printer ? configOptionsFor(printer.printer_profile_ids) : [];
                const auto = options.length === 1 ? Number(options[0].value) : null;
                onChange({ physicalPrinterId: pid, printerProfileId: auto });
              }}
            />
            <Dropdown
              size="sm"
              value={value.printerProfileId ?? ''}
              options={selectedPrinter ? configOptionsFor(selectedPrinter.printer_profile_ids) : []}
              placeholder={t('printerConfig.selectConfig')}
              emptyMessage={t('printerConfig.noConfigsForPrinter')}
              disabled={!selectedPrinter}
              onChange={(val) =>
                onChange({ ...value, printerProfileId: val === '' ? null : Number(val) })
              }
            />
          </>
        ) : (
          <Dropdown
            size="sm"
            value={value.printerProfileId ?? ''}
            options={configs.map((c) => ({ value: c.id, label: configLabel(c, t) }))}
            placeholder={t('printerConfig.selectConfig')}
            onChange={(val) =>
              onChange({ physicalPrinterId: null, printerProfileId: val === '' ? null : Number(val) })
            }
          />
        )}
      </div>
    </div>
  );
};
