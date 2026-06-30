// Единый набор цвет-функций (HEX/RGB/HSL). Используется FilamentPreview и
// HSLColorPicker — раньше было продублировано в обоих.

export const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

/** Нормализует HEX: добавляет #, раскрывает #rgb → #rrggbb, иначе fallback. */
export const sanitizeColor = (value?: string | null, fallback = '#FFFFFF'): string => {
  if (!value) return fallback;
  let color = value.trim();
  if (!color) return fallback;
  if (!color.startsWith('#')) {
    color = `#${color}`;
  }
  if (color.length === 4) {
    const [r, g, b] = color.slice(1);
    color = `#${r}${r}${g}${g}${b}${b}`;
  }
  if (color.length !== 7) {
    return fallback;
  }
  return color.toUpperCase();
};

export const hexToRgb = (hex: string): [number, number, number] => {
  const sanitized = sanitizeColor(hex);
  const r = parseInt(sanitized.slice(1, 3), 16);
  const g = parseInt(sanitized.slice(3, 5), 16);
  const b = parseInt(sanitized.slice(5, 7), 16);
  return [r, g, b];
};

export const rgbToHex = (r: number, g: number, b: number): string => {
  const toHex = (c: number) => clamp(Math.round(c), 0, 255).toString(16).padStart(2, '0');
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`.toUpperCase();
};

/** RGB (0..255) → HSL, где h,s,l нормализованы в 0..1. */
export const rgbToHsl = (r: number, g: number, b: number): [number, number, number] => {
  r /= 255;
  g /= 255;
  b /= 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h = 0;
  let s = 0;
  const l = (max + min) / 2;

  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r:
        h = (g - b) / d + (g < b ? 6 : 0);
        break;
      case g:
        h = (b - r) / d + 2;
        break;
      case b:
      default:
        h = (r - g) / d + 4;
        break;
    }
    h /= 6;
  }

  return [h, s, l];
};

/** HSL (0..1) → RGB (0..255). */
export const hslToRgb = (h: number, s: number, l: number): [number, number, number] => {
  if (s === 0) {
    const gray = Math.round(l * 255);
    return [gray, gray, gray];
  }

  const hue2rgb = (p: number, q: number, t: number) => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };

  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;

  const r = hue2rgb(p, q, h + 1 / 3);
  const g = hue2rgb(p, q, h);
  const b = hue2rgb(p, q, h - 1 / 3);

  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
};

export const adjustLightness = (hex: string, amount: number): string => {
  const [r, g, b] = hexToRgb(hex);
  const [h, s, l] = rgbToHsl(r, g, b);
  const newL = clamp(l + amount, 0, 1);
  const [nr, ng, nb] = hslToRgb(h, s, newL);
  return rgbToHex(nr, ng, nb);
};

export const getLuminance = (hex: string): number => {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
};

/** HEX → HSL, где h в градусах (0..360), s,l в процентах (0..100). */
export function hexToHsl(hex: string): { h: number; s: number; l: number } {
  const cleanHex = hex.replace('#', '');
  const r = parseInt(cleanHex.substring(0, 2), 16) / 255;
  const g = parseInt(cleanHex.substring(2, 4), 16) / 255;
  const b = parseInt(cleanHex.substring(4, 6), 16) / 255;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h = 0;
  let s = 0;
  const l = (max + min) / 2;

  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);

    switch (max) {
      case r:
        h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
        break;
      case g:
        h = ((b - r) / d + 2) / 6;
        break;
      case b:
        h = ((r - g) / d + 4) / 6;
        break;
    }
  }

  return {
    h: Math.round(h * 360),
    s: Math.round(s * 100),
    l: Math.round(l * 100),
  };
}

/** HSL (h в градусах, s,l в процентах) → HEX. */
export function hslToHex(h: number, s: number, l: number): string {
  h = h / 360;
  s = s / 100;
  l = l / 100;

  let r: number, g: number, b: number;

  if (s === 0) {
    r = g = b = l;
  } else {
    const hue2rgb = (p: number, q: number, t: number): number => {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };

    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;

    r = hue2rgb(p, q, h + 1 / 3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1 / 3);
  }

  const toHex = (x: number): string => {
    const hex = Math.round(x * 255).toString(16);
    return hex.length === 1 ? '0' + hex : hex;
  };

  return `#${toHex(r)}${toHex(g)}${toHex(b)}`.toUpperCase();
}
