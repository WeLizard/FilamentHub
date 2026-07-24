import { useTranslation } from 'react-i18next';
import { Settings, Edit, Eye } from 'lucide-react';
import type { PrinterProfile } from '../types/api';

/** One machine configuration (an Orca machine preset) as it appears both inside
 *  a printer card and in the tray of configurations not attached to a printer. */
export function PrinterConfigurationRow({
  profile,
  printProfileCount,
  onEdit,
  onView,
}: {
  profile: PrinterProfile;
  printProfileCount: number;
  onEdit?: (profile: PrinterProfile) => void;
  onView?: (profile: PrinterProfile) => void;
}) {
  const { t } = useTranslation();
  const nozzles = profile.nozzle_diameters ?? [];

  return (
    <div className="flex items-start gap-2 rounded-lg bg-white/5 border border-white/10 px-2.5 py-2">
      <Settings className="mt-0.5 h-4 w-4 flex-shrink-0 text-blue-400" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-white">{profile.name}</p>
        <p className="mt-0.5 text-[11px] text-gray-400">
          {nozzles.length > 0
            ? `${t('profilePage.nozzles')}: ${nozzles.join(', ')} ${t('profilePage.mm')}`
            : t('myPrinters.noNozzles')}
          {printProfileCount > 0 && ` · ${t('profilePage.printProfilesCount', { count: printProfileCount })}`}
        </p>
      </div>
      <div className="flex flex-shrink-0 items-center gap-1">
        {onView && (
          <button
            type="button"
            onClick={() => onView(profile)}
            className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-white/10 hover:text-white"
            title={t('profilePage.view')}
          >
            <Eye className="h-3.5 w-3.5" />
          </button>
        )}
        {onEdit && (
          <button
            type="button"
            onClick={() => onEdit(profile)}
            className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-white/10 hover:text-white"
            title={t('profilePage.edit')}
          >
            <Edit className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}
