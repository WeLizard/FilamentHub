import { useTranslation } from 'react-i18next';

import { OTHER_MATERIAL_BASE, materialBaseLabel } from '../../../utils/materialTypeGroups';

/** What the server resolved the manufacturer's material type to; both null when unrecognised. */
export interface MaterialClass {
  base: string | null;
  subtype: string | null;
}

const recognised = (value: MaterialClass) => value.base !== null && value.base !== OTHER_MATERIAL_BASE;

/** "→ PLA / PLA+" beside a group heading, or the full sentence under the material field. */
export function MaterialClassification({ value, compact = false }: { value: MaterialClass; compact?: boolean }) {
  const { t } = useTranslation();
  if (!recognised(value)) {
    return <span className="text-amber-300">{t('adminCatalogImport.curation.materialUnrecognised')}</span>;
  }
  const base = materialBaseLabel(t, value.base);
  const subtype = value.subtype && value.subtype !== value.base ? value.subtype : null;
  if (compact) return <span className="text-gray-400">→ {base}{subtype ? ` / ${subtype}` : ''}</span>;
  return <span className="text-gray-400">
    {subtype
      ? t('adminCatalogImport.curation.materialResolved', { base, subtype })
      : t('adminCatalogImport.curation.materialResolvedBase', { base })}
  </span>;
}
