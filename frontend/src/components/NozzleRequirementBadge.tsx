import { Hammer } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { InfoHint } from './InfoHint';
import { isNozzleTooSoft } from '../utils/nozzleHardness';

const HARDENED_HRC = 50;

interface NozzleRequirementBadgeProps {
  requiredHrc?: number | null;
  configuredHrc?: number | null;
  compact?: boolean;
  size?: 'chip' | 'tight';
  className?: string;
}

const SIZE_CLASSES: Record<'chip' | 'tight', string> = {
  chip: 'px-2 py-0.5 sm:py-1 text-xs',
  tight: 'px-1.5 py-0.5 text-[10px]',
};

export const NozzleRequirementBadge: React.FC<NozzleRequirementBadgeProps> = ({
  requiredHrc,
  configuredHrc,
  compact = false,
  size = 'chip',
  className = '',
}) => {
  const { t } = useTranslation();

  if (requiredHrc == null || requiredHrc < HARDENED_HRC) {
    return null;
  }

  const tooSoft = isNozzleTooSoft(requiredHrc, configuredHrc);
  const label = `HRC ≥ ${requiredHrc}`;
  const tone = tooSoft
    ? 'border-red-400/40 bg-red-500/15 text-red-200'
    : 'border-amber-400/30 bg-amber-500/15 text-amber-200';
  const title = tooSoft
    ? t('nozzleHardness.tooSoft', { required: requiredHrc, configured: configuredHrc })
    : `${t('nozzleHardness.badge')} · ${label}`;

  return (
    <span
      className={`inline-flex flex-shrink-0 items-center gap-1 rounded-full border font-medium ${SIZE_CLASSES[size]} ${tone} ${className}`}
      title={title}
    >
      <Hammer className="h-3 w-3" aria-hidden />
      {label}
      {!compact && (
        <InfoHint text={tooSoft ? `${title} ${t('paramHints.nozzleHardness')}` : t('paramHints.nozzleHardness')} />
      )}
    </span>
  );
};
