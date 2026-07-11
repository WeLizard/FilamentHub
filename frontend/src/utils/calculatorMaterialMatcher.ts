import type { CalculatorGcodeParseResponse, CalculatorParsedMaterial } from '../types/api';

export type MaterialMatchConfidence = 'high' | 'medium' | 'low';

export interface MaterialCandidateFields {
  name: string | null | undefined;
  vendor: string | null | undefined;
  materialType: string | null | undefined;
  color: string | null | undefined;
}

export interface MaterialMatch<T> {
  item: T;
  score: number;
  confidence: MaterialMatchConfidence;
}

export type PrioritizedMaterialMatch<TUser, TCatalog> =
  | { source: 'user'; match: MaterialMatch<TUser> }
  | { source: 'catalog'; match: MaterialMatch<TCatalog> };

const MIN_AUTO_MATCH_SCORE = 8;
const MIN_UNAMBIGUOUS_MARGIN = 2;

const MATERIAL_NOISE_TOKENS = new Set([
  'generic',
  'system',
  'copy',
  'copied',
  'копировать',
  'копия',
  'filamenthub',
]);

const normalizeMaterialText = (value: string | null | undefined): string =>
  (value ?? '')
    .toLowerCase()
    .replace(/[\[\](){}"'`@.,;:/\\|+-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const materialTokens = (value: string | null | undefined): string[] =>
  normalizeMaterialText(value)
    .split(' ')
    .map((token) => token.trim())
    .filter((token) => token.length > 1 && !MATERIAL_NOISE_TOKENS.has(token));

const countSharedTokens = (left: string[], right: string[]): number => {
  if (left.length === 0 || right.length === 0) {
    return 0;
  }

  const rightSet = new Set(right);
  return left.reduce((count, token) => count + (rightSet.has(token) ? 1 : 0), 0);
};

export const scoreMaterialCandidate = (
  parsed: CalculatorParsedMaterial,
  candidate: MaterialCandidateFields,
): number => {
  let score = 0;

  const parsedType = normalizeMaterialText(parsed.type);
  const candidateType = normalizeMaterialText(candidate.materialType);
  const parsedVendor = normalizeMaterialText(parsed.vendor);
  const candidateVendor = normalizeMaterialText(candidate.vendor);
  const parsedName = normalizeMaterialText(parsed.name);
  const candidateName = normalizeMaterialText(candidate.name);
  const parsedColor = normalizeMaterialText(parsed.color);
  const candidateColor = normalizeMaterialText(candidate.color);

  if (parsedType && candidateType) {
    if (parsedType === candidateType) {
      score += 6;
    } else {
      const sharedTypeTokens = countSharedTokens(materialTokens(parsed.type), materialTokens(candidate.materialType));
      score += Math.min(sharedTypeTokens * 2, 4);
    }
  }

  if (parsedVendor && candidateVendor) {
    if (parsedVendor === candidateVendor) {
      score += 4;
    } else {
      const sharedVendorTokens = countSharedTokens(materialTokens(parsed.vendor), materialTokens(candidate.vendor));
      score += Math.min(sharedVendorTokens * 2, 3);
    }
  }

  if (parsedName && candidateName) {
    if (parsedName === candidateName) {
      score += 8;
    } else if (parsedName.includes(candidateName) || candidateName.includes(parsedName)) {
      score += 6;
    } else {
      const sharedNameTokens = countSharedTokens(materialTokens(parsed.name), materialTokens(candidate.name));
      score += Math.min(sharedNameTokens * 2, 6);
    }
  }

  if (parsedColor && candidateColor && parsedColor === candidateColor) {
    score += 1;
  }

  return score;
};

const confidenceForScore = (score: number): MaterialMatchConfidence => {
  if (score >= 16) return 'high';
  if (score >= 10) return 'medium';
  return 'low';
};

export const findBestMaterialMatch = <T,>(
  items: T[],
  parsed: CalculatorParsedMaterial,
  getCandidate: (item: T) => MaterialCandidateFields,
): MaterialMatch<T> | null => {
  const ranked = items
    .map((item) => ({ item, score: scoreMaterialCandidate(parsed, getCandidate(item)) }))
    .filter((entry) => entry.score >= MIN_AUTO_MATCH_SCORE)
    .sort((left, right) => right.score - left.score);

  if (ranked.length === 0) {
    return null;
  }

  const [best, second] = ranked;
  if (second && best.score - second.score < MIN_UNAMBIGUOUS_MARGIN) {
    return null;
  }

  return {
    ...best,
    confidence: confidenceForScore(best.score),
  };
};

export const findPrioritizedMaterialMatch = <TUser, TCatalog>(
  parsed: CalculatorParsedMaterial,
  userItems: TUser[],
  catalogItems: TCatalog[],
  getUserCandidate: (item: TUser) => MaterialCandidateFields,
  getCatalogCandidate: (item: TCatalog) => MaterialCandidateFields,
): PrioritizedMaterialMatch<TUser, TCatalog> | null => {
  const userMatch = findBestMaterialMatch(userItems, parsed, getUserCandidate);
  if (userMatch) {
    return { source: 'user', match: userMatch };
  }

  const catalogMatch = findBestMaterialMatch(catalogItems, parsed, getCatalogCandidate);
  return catalogMatch ? { source: 'catalog', match: catalogMatch } : null;
};

export const pickPrimaryParsedMaterial = (
  parsed: CalculatorGcodeParseResponse | null,
): CalculatorParsedMaterial | null => {
  if (!parsed) {
    return null;
  }

  if (parsed.active_material_count != null && parsed.active_material_count > 1) {
    return null;
  }

  return (
    parsed.materials.find((material) => (material.weight_g ?? 0) > 0 || (material.length_mm ?? 0) > 0) ??
    parsed.materials[0] ??
    null
  );
};
