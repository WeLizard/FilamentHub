// Типичная плотность (г/см³) по типу материала + стандартные диаметры прутка.
// Единый источник для формы филамента и палитры.

export const MATERIAL_DENSITY: Record<string, number> = {
  // ── PLA family ──
  PLA: 1.24, 'PLA+': 1.24, 'PLA PRO': 1.24, 'PLA PRO+': 1.24, 'PLA MAX': 1.24,
  'PLA-AERO': 0.80, 'PLA-CF': 1.29,
  // ── PET / PETG family ──
  PET: 1.38, 'PET-CF': 1.41, 'PET-GF': 1.53,
  PETG: 1.27, 'PETG-CF': 1.32, 'PETG-GF': 1.45, PCTG: 1.23,
  // ── ABS / ASA / HIPS ──
  ABS: 1.04, 'ABS-CF': 1.11, 'ABS-GF': 1.20,
  ASA: 1.07, 'ASA-AERO': 0.82, 'ASA-CF': 1.13, 'ASA-GF': 1.23,
  HIPS: 1.04,
  // ── Nylon / PA family ──
  PA: 1.14, 'PA-CF': 1.18, 'PA-GF': 1.35,
  PA6: 1.14, 'PA6-CF': 1.18, 'PA6-GF': 1.36,
  PA11: 1.04, 'PA11-CF': 1.10, 'PA11-GF': 1.26,
  PA12: 1.02, 'PA12-CF': 1.09, 'PA12-GF': 1.24,
  PAHT: 1.14, 'PAHT-CF': 1.18, 'PAHT-GF': 1.35,
  // ── PC family ──
  PC: 1.20, 'PC-CF': 1.24, 'PC-ABS': 1.12, 'PC-PBT': 1.21,
  // ── PP family ──
  PP: 0.90, 'PP+': 0.91, 'PP PLUS': 0.91, 'PP-CF': 0.98,
  // ── PPA family ──
  PPA: 1.14, 'PPA-CF': 1.21, 'PPA-GF': 1.36,
  // ── High-temp / engineering ──
  PEEK: 1.30, 'PEEK-CF': 1.34, 'PEEK-GF': 1.49,
  PEKK: 1.30, 'PEKK-CF': 1.34,
  PEI: 1.27, 'PEI-1010': 1.27, 'PEI-1010-CF': 1.31, 'PEI-1010-GF': 1.44,
  'PEI-9085': 1.34, 'PEI-9085-CF': 1.37, 'PEI-9085-GF': 1.51,
  PPS: 1.35, PPSU: 1.29, PSU: 1.24, PES: 1.37,
  PI: 1.42, TPI: 1.37,
  // ── Flexible ──
  TPU: 1.21, FLEX: 1.20, EVA: 0.94,
  // ── Support / soluble ──
  PVA: 1.19, BVOH: 1.14, PVB: 1.08,
  // ── Other ──
  PE: 0.95, 'PE-CF': 1.03, 'PE-GF': 1.15,
  POM: 1.41, PHA: 1.25, PVDF: 1.78,
  PCL: 1.15, SBS: 1.01,
};

/** Плотность по типу материала (с учётом регистра), undefined если не известна. */
export function densityForMaterial(materialType: string): number | undefined {
  const mt = materialType.trim();
  if (!mt) return undefined;
  return MATERIAL_DENSITY[mt] ?? MATERIAL_DENSITY[mt.toUpperCase()];
}

/** Стандартные диаметры прутка. */
export const STANDARD_DIAMETERS = [1.75, 2.85, 3.0] as const;
