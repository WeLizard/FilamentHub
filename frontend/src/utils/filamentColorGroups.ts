import type { FilamentColorGroup } from '../types/api';

export const FILAMENT_COLOR_GROUPS: readonly FilamentColorGroup[] = [
  'black',
  'white',
  'gray',
  'red',
  'orange',
  'yellow',
  'green',
  'blue',
  'purple',
  'pink',
  'brown',
  'gold',
  'silver',
];

export const FILAMENT_COLOR_GROUP_PALETTE: Record<FilamentColorGroup, readonly string[]> = {
  black: ['#000000', '#111827', '#1F2937', '#2B2B2B'],
  white: ['#FFFFFF', '#FAFAF9', '#F5F5F4', '#FFF7ED'],
  gray: ['#4B5563', '#6B7280', '#9CA3AF', '#D1D5DB'],
  red: ['#7F1D1D', '#B91C1C', '#EF4444', '#F87171', '#FF0000'],
  orange: ['#9A3412', '#C2410C', '#F97316', '#FB923C', '#FF7A00'],
  yellow: ['#A16207', '#CA8A04', '#EAB308', '#FACC15', '#FFD900'],
  green: ['#14532D', '#15803D', '#22C55E', '#4ADE80', '#00A651', '#008080'],
  blue: ['#172554', '#1D4ED8', '#3B82F6', '#60A5FA', '#0066FF', '#00FFFF'],
  purple: ['#4C1D95', '#6D28D9', '#8B5CF6', '#A855F7', '#7C3AED', '#800080'],
  pink: ['#831843', '#BE185D', '#EC4899', '#F472B6', '#FF69B4', '#FFB6C1'],
  brown: ['#3F2D20', '#5C3A21', '#7C4A2D', '#8B5E3C', '#8B4513', '#A52A2A'],
  gold: ['#806000', '#A67C00', '#B8860B', '#D4AF37', '#E5C158'],
  silver: ['#707780', '#8E959E', '#A7ADB5', '#C0C0C0', '#D5D8DC'],
};

// Muted references are used only for classification. Keeping them separate
// preserves the compact palette shown to contributors in the editor.
const MUTED_COLOR_ANCHORS: Partial<Record<FilamentColorGroup, readonly string[]>> = {
  orange: ['#E64A19', '#F4511E'],
  green: ['#556B2F', '#6B7D52', '#8A9A5B', '#BFD8A6'],
  blue: ['#78909C', '#90A4AE'],
  pink: ['#B76E79', '#C58F89', '#D8A39D'],
  brown: ['#B87333', '#B8895A', '#C2A277', '#D2B48C'],
};

export const MULTICOLOR_TYPES = ['two', 'three', 'gradient', 'transition'] as const;

const CHROMATIC_COLOR_GROUPS = FILAMENT_COLOR_GROUPS.filter(
  (group) => !['black', 'white', 'gray', 'silver'].includes(group),
);
const NON_METALLIC_CHROMATIC_COLOR_GROUPS = CHROMATIC_COLOR_GROUPS.filter(
  (group) => group !== 'gold',
);
const NEUTRAL_CHROMA_MAX = 0.035;

type Oklab = readonly [number, number, number];

const hexToOklab = (colorHex: string): Oklab | null => {
  const match = /^#?([0-9a-f]{6})$/i.exec(colorHex.trim());
  if (!match) return null;

  const value = match[1];
  const linear = (channel: number) => {
    const normalized = channel / 255;
    return normalized <= 0.04045
      ? normalized / 12.92
      : ((normalized + 0.055) / 1.055) ** 2.4;
  };
  const red = linear(Number.parseInt(value.slice(0, 2), 16));
  const green = linear(Number.parseInt(value.slice(2, 4), 16));
  const blue = linear(Number.parseInt(value.slice(4, 6), 16));
  const coneL = Math.cbrt(0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue);
  const coneM = Math.cbrt(0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue);
  const coneS = Math.cbrt(0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue);

  return [
    0.2104542553 * coneL + 0.793617785 * coneM - 0.0040720468 * coneS,
    1.9779984951 * coneL - 2.428592205 * coneM + 0.4505937099 * coneS,
    0.0259040371 * coneL + 0.7827717662 * coneM - 0.808675766 * coneS,
  ];
};

const createOklabPalette = (): Record<FilamentColorGroup, readonly Oklab[]> => {
  const palette = {} as Record<FilamentColorGroup, readonly Oklab[]>;
  for (const group of FILAMENT_COLOR_GROUPS) {
    palette[group] = [
      ...FILAMENT_COLOR_GROUP_PALETTE[group],
      ...(MUTED_COLOR_ANCHORS[group] ?? []),
    ].map((hex) => hexToOklab(hex) as Oklab);
  }
  return palette;
};

const OKLAB_PALETTE = createOklabPalette();

export const classifyFilamentColorGroup = (
  colorHex: string,
  metallic = false,
): FilamentColorGroup | null => {
  const sample = hexToOklab(colorHex);
  if (!sample) return null;

  const [lightness, axisA, axisB] = sample;
  const chroma = Math.hypot(axisA, axisB);
  if (lightness <= 0.2 || (lightness <= 0.28 && chroma <= 0.08)) return 'black';
  if (lightness >= 0.93 && chroma <= 0.04) return 'white';
  if (chroma <= NEUTRAL_CHROMA_MAX) return metallic ? 'silver' : 'gray';

  const groups = metallic ? CHROMATIC_COLOR_GROUPS : NON_METALLIC_CHROMATIC_COLOR_GROUPS;
  let closest: FilamentColorGroup | null = null;
  let closestDistance = Number.POSITIVE_INFINITY;
  for (const group of groups) {
    const distance = Math.min(
      ...OKLAB_PALETTE[group].map((anchor) =>
        sample.reduce(
          (sum, component, index) => sum + (component - anchor[index]) ** 2,
          0,
        ),
      ),
    );
    if (distance < closestDistance) {
      closest = group;
      closestDistance = distance;
    }
  }
  return closest;
};
