import React from 'react';
import { useTranslation } from 'react-i18next';
import { Grid3x3, List } from 'lucide-react';

export type ViewMode = 'grid' | 'list';

interface ViewModeToggleProps {
  value: ViewMode;
  onChange: (mode: ViewMode) => void;
  className?: string;
  gridLabel?: string;
  listLabel?: string;
  ariaLabel?: string;
  showLabels?: boolean;
}

export const ViewModeToggle: React.FC<ViewModeToggleProps> = ({
  value,
  onChange,
  className = '',
  gridLabel,
  listLabel,
  ariaLabel,
  showLabels = false,
}) => {
  const { t } = useTranslation();
  const resolvedGridLabel = gridLabel ?? t('common.gridView');
  const resolvedListLabel = listLabel ?? t('common.listView');

  const buttonClass = (mode: ViewMode) => `${showLabels ? 'inline-flex items-center gap-2 px-3 py-2' : 'p-2'} rounded transition-all ${
    value === mode ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'
  }`;

  return (
    <div
      className={`flex items-center rounded-lg border border-white/20 bg-white/10 p-1 ${className}`}
      role="group"
      aria-label={ariaLabel}
    >
      <button
        type="button"
        onClick={() => onChange('grid')}
        className={buttonClass('grid')}
        title={resolvedGridLabel}
        aria-pressed={value === 'grid'}
      >
        <Grid3x3 className="w-4 h-4" aria-hidden />
        {showLabels && <span>{resolvedGridLabel}</span>}
      </button>
      <button
        type="button"
        onClick={() => onChange('list')}
        className={buttonClass('list')}
        title={resolvedListLabel}
        aria-pressed={value === 'list'}
      >
        <List className="w-4 h-4" aria-hidden />
        {showLabels && <span>{resolvedListLabel}</span>}
      </button>
    </div>
  );
};
