import { useTranslation } from 'react-i18next';
import type { Preset } from '../types/api';

/** Tested-on evidence is displayed separately from a user's installation scope. */
export function PresetTestedOn({
  printers,
  className = '',
}: {
  printers: Preset['printers'];
  className?: string;
}) {
  const { t } = useTranslation();
  if (!printers?.length) return null;

  return (
    <div className={`flex flex-wrap items-center gap-1.5 text-xs text-gray-300 ${className}`}>
      <span>{t('viewPreset.testedOn')}:</span>
      {printers.map((printer) => (
        <span
          key={printer.id}
          className="px-2 py-0.5 bg-white/10 rounded-md border border-white/20"
          title={printer.name}
        >
          {printer.name}
        </span>
      ))}
    </div>
  );
}
