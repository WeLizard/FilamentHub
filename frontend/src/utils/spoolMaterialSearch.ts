import type { Filament } from '../types/api';

const normalize = (text: string) => text.normalize('NFKC').toLowerCase()
  .replace(/ё/g, 'е').replace(/(\d),(\d)/g, '$1.$2').replace(/(\d)\s*(?:mm|мм)(?![\p{L}\p{N}])/gu, '$1').trim();
const words = (text: string) => (normalize(text).match(/[\p{L}\p{N}]+(?:[.+][\p{L}\p{N}]+)*\+*/gu) ?? [])
  .map(word => /^\d+\.\d+$/.test(word) ? word.replace(/0+$/, '').replace(/\.$/, '') : word);

export function rankSpoolMaterials(
  search: string,
  shelfIds: readonly number[],
  shelfMaterials: readonly Filament[],
  presetMaterials: readonly Filament[],
  catalogMaterials: readonly Filament[],
) {
  const query = normalize(search);
  const terms = [...new Set(words(query))];
  const shelfOrder = new Map(shelfIds.map((id, index) => [id, index]));
  const presets = new Set(presetMaterials.map(item => item.id));
  const fromCatalog = new Set(catalogMaterials.map(item => item.id));
  const unique = new Map([...presetMaterials, ...catalogMaterials, ...shelfMaterials].map(item => [item.id, item]));

  return [...unique.values()].filter(item => item.active !== false).flatMap(item => {
    const fields = [
      item.brand_name, item.name, item.line_name, item.material_type, item.color_name,
      item.color_hex, item.diameter == null ? null : `${item.diameter} mm мм`,
    ].filter((field): field is string => typeof field === 'string').map(normalize);
    const itemTerms = new Set(fields.flatMap(words));
    const exact = terms.filter(term => itemTerms.has(term)).length;
    const prefix = terms.filter(term => itemTerms.has(term) ||
      (term.length >= 2 && [...itemTerms].some(word => word.startsWith(term)))).length;
    if (terms.length && !prefix && !fromCatalog.has(item.id)) return [];
    const match = !terms.length ? 0 : fields.includes(query) ? 3
      : exact === terms.length ? 2 : prefix === terms.length ? 1 : 0;
    const shelfIndex = shelfOrder.get(item.id) ?? shelfIds.length;
    const origin = shelfOrder.has(item.id) ? 'shelf' : presets.has(item.id) ? 'preset' : 'catalog';
    const priority = origin === 'shelf' ? 2 : origin === 'preset' ? 1 : 0;
    return [{ item, match, exact, prefix, priority, shelfIndex, origin, similar: terms.length > 0 && match < 2 }];
  }).sort((left, right) => right.match - left.match || right.exact - left.exact ||
    right.prefix - left.prefix || right.priority - left.priority || left.shelfIndex - right.shelfIndex ||
    left.item.name.localeCompare(right.item.name) || left.item.id - right.item.id).slice(0, 10);
}
