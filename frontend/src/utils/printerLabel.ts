import type { Printer } from '../types/api';

function compact(value: string | null | undefined): string {
  return (value ?? '').trim().replace(/\s+/g, ' ');
}

function comparable(value: string): string {
  return compact(value).toLocaleLowerCase();
}

/** System models keep their exact catalog name; custom models may have a display alias. */
export function printerCatalogLabel(
  printer: Pick<Printer, 'manufacturer' | 'model' | 'name' | 'source'>,
): string {
  if (printer.source === 'system') return printer.name;
  const manufacturer = compact(printer.manufacturer);
  const model = compact(printer.model);
  const name = compact(printer.name);
  const base = manufacturer && model
    ? comparable(model).startsWith(`${comparable(manufacturer)} `)
      ? model
      : `${manufacturer} ${model}`
    : model || manufacturer || name;

  if (!name || comparable(name) === comparable(model) || comparable(name) === comparable(base)) {
    return base;
  }
  return base ? `${base} (${name})` : name;
}
