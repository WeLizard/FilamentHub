import React from 'react';
import { useTranslation } from 'react-i18next';
import { Grid3x3, List } from 'lucide-react';

export type ViewMode = 'grid' | 'list';

interface ViewModeToggleProps {
  value: ViewMode;
  onChange: (mode: ViewMode) => void;
  className?: string;
}

export const ViewModeToggle: React.FC<ViewModeToggleProps> = ({ value, onChange, className = '' }) => {
  const { t } = useTranslation();

  const buttonClass = (mode: ViewMode) => `p-2 rounded transition-all ${
    value === mode ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'
  }`;

  return (
    <div className={`flex items-center rounded-lg border border-white/20 bg-white/10 p-1 ${className}`}>
      <button
        type="button"
        onClick={() => onChange('grid')}
        className={buttonClass('grid')}
        title={t('common.gridView')}
        aria-pressed={value === 'grid'}
      >
        <Grid3x3 className="w-4 h-4" />
      </button>
      <button
        type="button"
        onClick={() => onChange('list')}
        className={buttonClass('list')}
        title={t('common.listView')}
        aria-pressed={value === 'list'}
      >
        <List className="w-4 h-4" />
      </button>
    </div>
  );
};
