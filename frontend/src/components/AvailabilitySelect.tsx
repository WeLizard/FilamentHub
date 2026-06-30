/** Общий выбор статуса наличия материала. «Снят с производства» показываем
 *  только при редактировании (includeDiscontinued). */

import { useTranslation } from 'react-i18next';
import { Dropdown } from './Dropdown';
import type { FilamentAvailability } from '../types/api';

interface AvailabilitySelectProps {
  value: FilamentAvailability;
  onChange: (value: FilamentAvailability) => void;
  /** Показывать «Снят с производства» (обычно только при редактировании). */
  includeDiscontinued?: boolean;
  label?: string;
}

export function AvailabilitySelect({ value, onChange, includeDiscontinued = false, label }: AvailabilitySelectProps) {
  const { t } = useTranslation();
  return (
    <Dropdown
      label={label ?? t('createFilament.availabilityLabel')}
      value={value}
      options={[
        { value: 'available', label: t('createFilament.availability.available') },
        ...(includeDiscontinued ? [{ value: 'discontinued', label: t('createFilament.availability.discontinued') }] : []),
        { value: 'coming_soon', label: t('createFilament.availability.coming_soon') },
      ]}
      onChange={(val) => onChange(val as FilamentAvailability)}
    />
  );
}
