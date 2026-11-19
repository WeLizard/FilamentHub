import React from 'react';
import { useTranslation } from 'react-i18next';
import { Grid3x3, List } from 'lucide-react';
import { SegmentedToggle } from './SegmentedToggle';

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
  return (
    <SegmentedToggle
      value={value}
      onChange={onChange}
      options={[
        { value: 'grid', label: gridLabel ?? t('common.gridView'), icon: Grid3x3 },
        { value: 'list', label: listLabel ?? t('common.listView'), icon: List },
      ]}
      ariaLabel={ariaLabel}
      showLabels={showLabels}
      className={className}
    />
  );
};
