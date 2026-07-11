import React from 'react';
import { useTranslation } from 'react-i18next';
import { CustomSelect } from './CustomSelect';

/**
 * Nozzle type → required nozzle hardness (Orca `required_nozzle_HRC`, a minimum
 * threshold). A material property: abrasive fillers wear soft brass, so they
 * require a hardened nozzle. Users pick a familiar nozzle type; we store/export
 * its HRC number. Values from real hardness data (hardened steel HRC 55–65,
 * tungsten carbide HRC ~69–81); brass is soft = no requirement (0).
 */
export const NOZZLE_TYPE_OPTIONS: { hrc: number; key: string }[] = [
  { hrc: 0, key: 'brass' },
  { hrc: 50, key: 'hardenedSteel' },
  { hrc: 60, key: 'ruby' },
  { hrc: 70, key: 'tungstenCarbide' },
];

// Fillers abrasive enough to wear a soft nozzle → recommend a hardened one.
// Subset of KNOWN_FILLERS (glitter/patterns are decorative, not abrasive).
const ABRASIVE_FILLERS = new Set([
  'carbon', 'glass', 'fibers', 'metallic', 'luminescent', 'wood', 'stone',
]);

// Below this HRC a nozzle is considered soft (brass) for the abrasive hint.
const HARDENED_HRC = 50;

export const NozzleHardnessField: React.FC<{
  value: number | null;
  onChange: (value: number | null) => void;
  filler?: string | null;
}> = ({ value, onChange, filler }) => {
  const { t } = useTranslation();

  const options = [
    { value: 'none', label: t('nozzleHardness.notSet') },
    ...NOZZLE_TYPE_OPTIONS.map((o) => ({
      value: String(o.hrc),
      label: `${t(`nozzleHardness.${o.key}`)} · HRC ${o.hrc}`,
    })),
  ];

  const abrasive = !!filler && ABRASIVE_FILLERS.has(filler);
  const showHint = abrasive && (value === null || value < HARDENED_HRC);

  return (
    <div>
      <label className="block text-gray-300 mb-1 text-sm font-medium">
        {t('nozzleHardness.label')}
      </label>
      <p className="text-gray-400 text-xs mb-2">{t('nozzleHardness.hint')}</p>
      <CustomSelect
        value={value === null ? 'none' : String(value)}
        onChange={(v) => onChange(v === 'none' || v === null ? null : Number(v))}
        options={options}
      />
      {showHint && (
        <p className="mt-2 text-xs text-amber-300">{t('nozzleHardness.abrasiveHint')}</p>
      )}
    </div>
  );
};
