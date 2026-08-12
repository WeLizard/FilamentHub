import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronUp, Download, Edit, Eye, Plus, Settings } from 'lucide-react';
import type { PrinterProfile, PrintProfile } from '../types/api';

export interface ConfigurationPrintProfile {
  profile: PrintProfile;
  exact: boolean;
}

/** One machine configuration (an Orca machine preset) as it appears both inside
 *  a printer card and in the tray of configurations not attached to a printer. */
export function PrinterConfigurationRow({
  profile,
  printProfiles,
  currentUserId,
  onEdit,
  onView,
  onViewPrintProfile,
  onEditPrintProfile,
  onCreatePrintProfile,
  onDownloadPrintProfile,
}: {
  profile: PrinterProfile;
  printProfiles: ConfigurationPrintProfile[];
  currentUserId?: number | null;
  onEdit?: (profile: PrinterProfile) => void;
  onView?: (profile: PrinterProfile) => void;
  onViewPrintProfile?: (profile: PrintProfile) => void;
  onEditPrintProfile?: (
    profile: PrintProfile,
    configuration: PrinterProfile,
  ) => void;
  onCreatePrintProfile?: (configuration: PrinterProfile) => void;
  onDownloadPrintProfile?: (profile: PrintProfile) => void;
}) {
  const { t } = useTranslation();
  const [printProfilesOpen, setPrintProfilesOpen] = useState(false);
  const nozzles = profile.nozzle_diameters ?? [];
  const canEditConfiguration = Boolean(
    onEdit &&
    !profile.is_official &&
    profile.owner_user_id === currentUserId,
  );
  const canOpenPrintProfiles = Boolean(
    onCreatePrintProfile || printProfiles.length > 0,
  );

  return (
    <div className="rounded-lg border border-white/10 bg-white/5">
      <div className="flex items-start gap-2 px-2.5 py-2">
        <Settings className="mt-0.5 h-4 w-4 flex-shrink-0 text-blue-400" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium text-white">{profile.name}</p>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-gray-400">
            <span>
              {nozzles.length > 0
                ? `${t('profilePage.nozzles')}: ${nozzles.join(', ')} ${t('profilePage.mm')}`
                : t('myPrinters.noNozzles')}
            </span>
            {canOpenPrintProfiles && (
              <button
                type="button"
                onClick={() => setPrintProfilesOpen((open) => !open)}
                className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-purple-200 transition-colors hover:bg-purple-500/15 hover:text-white"
                aria-expanded={printProfilesOpen}
              >
                {t('profilePage.printProfilesCount', { count: printProfiles.length })}
                {printProfilesOpen ? (
                  <ChevronUp className="h-3 w-3" />
                ) : (
                  <ChevronDown className="h-3 w-3" />
                )}
              </button>
            )}
          </div>
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
          {canEditConfiguration && (
            <button
              type="button"
              onClick={() => onEdit?.(profile)}
              className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-white/10 hover:text-white"
              title={t('profilePage.edit')}
            >
              <Edit className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {printProfilesOpen && (
        <div className="space-y-1.5 border-t border-white/10 px-2.5 py-2">
          {printProfiles.map(({ profile: printProfile, exact }) => (
            <div
              key={printProfile.id}
              className="flex items-start gap-2 rounded-md border border-white/10 bg-black/10 px-2 py-1.5"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-[11px] font-medium text-white">
                  {printProfile.name}
                </p>
                <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[10px] text-gray-400">
                  {printProfile.layer_height_mm != null && (
                    <span>
                      {t('profilePage.layerHeight')}: {printProfile.layer_height_mm.toFixed(2)} {t('profilePage.mm')}
                    </span>
                  )}
                  {printProfile.quality_tier && <span>· {printProfile.quality_tier}</span>}
                  {!exact && (
                    <span className="rounded bg-amber-500/10 px-1 py-0.5 text-amber-200">
                      {t('myPrinters.compatibilityFallback')}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex flex-shrink-0 items-center gap-0.5">
                {onViewPrintProfile && (
                  <button
                    type="button"
                    onClick={() => onViewPrintProfile(printProfile)}
                    className="rounded p-1 text-gray-400 transition-colors hover:bg-white/10 hover:text-white"
                    title={t('profilePage.view')}
                  >
                    <Eye className="h-3 w-3" />
                  </button>
                )}
                {onEditPrintProfile &&
                  !printProfile.is_official &&
                  printProfile.owner_user_id === currentUserId && (
                    <button
                      type="button"
                      onClick={() => onEditPrintProfile(printProfile, profile)}
                      className="rounded p-1 text-gray-400 transition-colors hover:bg-white/10 hover:text-white"
                      title={t('profilePage.edit')}
                    >
                      <Edit className="h-3 w-3" />
                    </button>
                  )}
                {onDownloadPrintProfile && (
                  <button
                    type="button"
                    onClick={() => onDownloadPrintProfile(printProfile)}
                    className="rounded p-1 text-gray-400 transition-colors hover:bg-white/10 hover:text-white"
                    title={t('profilePage.download')}
                  >
                    <Download className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>
          ))}
          {onCreatePrintProfile && (
            <button
              type="button"
              onClick={() => onCreatePrintProfile(profile)}
              className="flex w-full items-center justify-center gap-1 rounded-md border border-dashed border-white/15 px-2 py-1.5 text-[11px] text-gray-400 transition-colors hover:border-white/30 hover:text-white"
            >
              <Plus className="h-3 w-3" />
              {t('profilePage.addPrintProfile')}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
