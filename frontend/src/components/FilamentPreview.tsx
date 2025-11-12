import React, { useMemo, useId } from 'react';
import { Thermometer } from 'lucide-react';
import type { FilamentVisualSettings } from '../types/api';

type SizeKey = 'small' | 'medium' | 'large';

const SIZE_CONFIG: Record<SizeKey, { height: number; bodyLength: number; strokeWidth: number }> = {
  small: { height: 40, bodyLength: 90, strokeWidth: 2 },
  medium: { height: 60, bodyLength: 120, strokeWidth: 3 },
  large: { height: 90, bodyLength: 200, strokeWidth: 4 },
};

const sanitizeColor = (value?: string | null, fallback = '#FFFFFF'): string => {
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

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

const hexToRgb = (hex: string): [number, number, number] => {
  const sanitized = sanitizeColor(hex);
  const r = parseInt(sanitized.slice(1, 3), 16);
  const g = parseInt(sanitized.slice(3, 5), 16);
  const b = parseInt(sanitized.slice(5, 7), 16);
  return [r, g, b];
};

const rgbToHex = (r: number, g: number, b: number): string => {
  const toHex = (c: number) => clamp(Math.round(c), 0, 255).toString(16).padStart(2, '0');
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`.toUpperCase();
};

const rgbToHsl = (r: number, g: number, b: number): [number, number, number] => {
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

const hslToRgb = (h: number, s: number, l: number): [number, number, number] => {
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

const adjustLightness = (hex: string, amount: number): string => {
  const [r, g, b] = hexToRgb(hex);
  const [h, s, l] = rgbToHsl(r, g, b);
  const newL = clamp(l + amount, 0, 1);
  const [nr, ng, nb] = hslToRgb(h, s, newL);
  return rgbToHex(nr, ng, nb);
};

const getLuminance = (hex: string): number => {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
};

type ExtraEndSegment = {
  startAngle: number;
  endAngle: number;
  color: string;
};

type ColorDefResult = {
  defs: React.ReactNode[];
  bodyFill: string;
  endFill: string;
  extraEndSegments?: ExtraEndSegment[];
};

const createColorDefinitions = (
  colors: string[],
  colorType: string,
  idPrefix: string,
  baseHexValue: string,
  bodyLength: number,
  bodyStart: number,
  bodyEnd: number,
  radius: number,
): ColorDefResult => {
  const defs: React.ReactNode[] = [];
  const normalizedPrimary = sanitizeColor(baseHexValue);
  const palette = colors.length > 0 ? colors : [normalizedPrimary];
  const bodyStartCoord = bodyEnd - bodyLength;
  const rawPaletteForType = (() => {
    switch (colorType) {
      case 'single':
        return [palette[0]];
      case 'two':
        return palette.slice(0, 2);
      case 'three':
        return palette.slice(0, 3);
      case 'transition':
      case 'thermochromic':
        return palette.slice(0, 2);
      case 'gradient':
        return palette.slice(0, Math.min(palette.length, 5));
      default:
        return palette;
    }
  })();
  const paletteForType = rawPaletteForType.length > 0
    ? [normalizedPrimary, ...rawPaletteForType.slice(1)]
    : [normalizedPrimary];
  let bodyFill = paletteForType[0];
  let endFill = paletteForType[0];
  let extraEndSegments: ExtraEndSegment[] | undefined;
  const ensure = (index: number) =>
    paletteForType[Math.min(index, paletteForType.length - 1)] ?? normalizedPrimary;
  const makeId = (name: string) => `${idPrefix}-${name}`;

  switch (colorType) {
    case 'two': {
      const gradId = makeId('body-two');
      defs.push(
        <linearGradient id={gradId} key={gradId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor={ensure(0)} />
          <stop offset="50%" stopColor={ensure(0)} />
          <stop offset="50%" stopColor={ensure(1)} />
          <stop offset="100%" stopColor={ensure(1)} />
        </linearGradient>,
      );
      bodyFill = `url(#${gradId})`;

      const endId = makeId('end-two');
      defs.push(
        <linearGradient id={endId} key={endId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor={ensure(0)} />
          <stop offset="50%" stopColor={ensure(0)} />
          <stop offset="50%" stopColor={ensure(1)} />
          <stop offset="100%" stopColor={ensure(1)} />
        </linearGradient>,
      );
      endFill = `url(#${endId})`;
      break;
    }
    case 'three': {
      const segmentId = makeId('three-segments');
      defs.push(
        <linearGradient id={segmentId} key={segmentId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor={ensure(0)} />
          <stop offset="72.5%" stopColor={ensure(0)} />
          <stop offset="72.5%" stopColor={ensure(1)} />
          <stop offset="100%" stopColor={ensure(1)} />
        </linearGradient>,
      );
      bodyFill = `url(#${segmentId})`;
      endFill = ensure(0);
      extraEndSegments = [
        { startAngle: 0, endAngle: 120, color: ensure(2) },
        { startAngle: 120, endAngle: 240, color: ensure(1) },
      ];
      break;
    }
    case 'gradient': {
      const gradientColors = paletteForType;
      if (gradientColors.length > 1) {
        const gradId = makeId('body-gradient');
        defs.push(
          <radialGradient
            id={gradId}
            key={gradId}
            cx={bodyEnd}
            cy={radius}
            r={bodyLength + radius}
            gradientUnits="userSpaceOnUse"
          >
            {gradientColors.map((color, index) => {
              const offset =
                gradientColors.length === 1
                  ? 1
                  : index === 0
                    ? 0
                    : 0.2 + ((index - 1) / (gradientColors.length - 1)) * 0.8;
              return (
                <stop key={`${gradId}-${index}`} offset={`${Math.min(offset, 1) * 100}%`} stopColor={color} />
              );
            })}
          </radialGradient>,
        );
        bodyFill = `url(#${gradId})`;
      } else {
        bodyFill = gradientColors[0];
      }
      endFill = gradientColors[0];
      break;
    }
    case 'transition': {
      const primary = ensure(0);
      const secondary = ensure(1);
      const gradId = makeId('transition-body');
      defs.push(
        <linearGradient
          id={gradId}
          key={gradId}
          x1={bodyEnd}
          y1={radius}
          x2={bodyStartCoord}
          y2={radius}
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0%" stopColor={primary} />
          <stop offset="100%" stopColor={secondary} />
        </linearGradient>,
      );
      bodyFill = `url(#${gradId})`;
      endFill = primary;
      break;
    }
    case 'thermochromic': {
      const primary = ensure(0);
      const secondary = ensure(1);
      const gradId = makeId(`${colorType}-body`);
      defs.push(
        <radialGradient id={gradId} key={gradId} cx="100%" cy="50%" r="120%">
          <stop offset="0%" stopColor={primary} />
          <stop offset="100%" stopColor={secondary} />
        </radialGradient>,
      );
      bodyFill = `url(#${gradId})`;

      const endId = makeId(`${colorType}-end`);
      defs.push(
        <radialGradient id={endId} key={endId} cx="35%" cy="35%" r="75%">
          <stop offset="0%" stopColor={primary} />
          <stop offset="100%" stopColor={secondary} />
        </radialGradient>,
      );
      endFill = `url(#${endId})`;
      break;
    }
    default: {
      bodyFill = ensure(0);
      endFill = ensure(paletteForType.length - 1);
    }
  }

  return { defs, bodyFill, endFill, extraEndSegments };
};

type FillerDefResult = {
  defs: React.ReactNode[];
  bodyPatternFill: string | null;
  endPatternFill: string | null;
  patternOpacity: number;
  glowFilterId: string | null;
};

const createFillerDefinitions = (filler: string, colors: string[], idPrefix: string): FillerDefResult => {
  const defs: React.ReactNode[] = [];
  let bodyPatternFill: string | null = null;
  let endPatternFill: string | null = null;
  let patternOpacity = 0.35;
  let glowFilterId: string | null = null;
  const makeId = (name: string) => `${idPrefix}-${name}`;

  const addStripePattern = (
    id: string,
    width: number,
    gap: number,
    angle: number,
    opacity = 0.25,
  ) => (
    <pattern
      id={id}
      key={id}
      width={width + gap}
      height={width + gap}
      patternUnits="userSpaceOnUse"
      patternTransform={`rotate(${angle})`}
    >
      <rect width={width} height={width + gap} fill="#FFFFFF" fillOpacity={opacity} />
    </pattern>
  );

  switch (filler) {
    case 'none':
      return { defs, bodyPatternFill, endPatternFill, patternOpacity, glowFilterId };
    case 'carbon': {
      const patternId = makeId('carbon');
      defs.push(
        <pattern id={patternId} key={patternId} width="8" height="8" patternUnits="userSpaceOnUse">
          <rect width="8" height="8" fill="#1A1A1A" />
          <path d="M0 0 L8 8 M8 0 L0 8" stroke="#2E2E2E" strokeWidth="1" strokeOpacity="0.6" fill="none" />
          <path d="M0 4 L8 4" stroke="#0F0F0F" strokeWidth="1" strokeOpacity="0.4" />
        </pattern>,
      );
      bodyPatternFill = `url(#${patternId})`;
      endPatternFill = bodyPatternFill;
      patternOpacity = 0.55;
      break;
    }
    case 'glass': {
      const patternId = makeId('glass');
      defs.push(
        <pattern
          id={patternId}
          key={patternId}
          width="6"
          height="8"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(-26)"
        >
          <rect width="2" height="8" fill="#FFFFFF" fillOpacity="0.25" />
        </pattern>,
      );
      bodyPatternFill = `url(#${patternId})`;
      endPatternFill = bodyPatternFill;
      patternOpacity = 0.45;
      break;
    }
    case 'metallic': {
      const base = sanitizeColor(colors[0] ?? '#999999');
      const light1 = adjustLightness(base, 0.18);
      const dark1 = adjustLightness(base, -0.18);
      const dark2 = adjustLightness(base, -0.35);
      const bodyGradient = makeId('metallic-body');
      const endGradient = makeId('metallic-end');
      defs.push(
        <linearGradient id={bodyGradient} key={bodyGradient} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor={light1} />
          <stop offset="25%" stopColor={dark1} />
          <stop offset="55%" stopColor={base} />
          <stop offset="100%" stopColor={dark2} />
        </linearGradient>,
      );
      defs.push(
        <radialGradient id={endGradient} key={endGradient} cx="45%" cy="45%" r="80%">
          <stop offset="0%" stopColor={light1} />
          <stop offset="40%" stopColor={dark1} />
          <stop offset="70%" stopColor={base} />
          <stop offset="100%" stopColor={dark2} />
        </radialGradient>,
      );
      bodyPatternFill = `url(#${bodyGradient})`;
      endPatternFill = `url(#${endGradient})`;
      patternOpacity = 1;
      break;
    }
    case 'wood': {
      const patternId = makeId('wood');
      defs.push(
        <pattern id={patternId} key={patternId} width="20" height="20" patternUnits="userSpaceOnUse">
          <rect width="20" height="20" fill="none" />
          <path d="M0 10 Q10 4 20 10" stroke="#a1887f" strokeWidth="2" strokeOpacity="0.35" fill="none" />
          <path d="M0 6 Q10 0 20 6" stroke="#d7ccc8" strokeWidth="1" strokeOpacity="0.25" fill="none" />
          <circle cx="6" cy="6" r="2" fill="#8d6e63" fillOpacity="0.25" />
          <circle cx="14" cy="14" r="3" fill="#6d4c41" fillOpacity="0.25" />
        </pattern>,
      );
      bodyPatternFill = `url(#${patternId})`;
      endPatternFill = bodyPatternFill;
      patternOpacity = 0.5;
      break;
    }
    case 'glitter': {
      const patternId = makeId('glitter');
      defs.push(
        <pattern id={patternId} key={patternId} width="24" height="24" patternUnits="userSpaceOnUse">
          <circle cx="6" cy="6" r="1.6" fill="#FFFFFF" fillOpacity="0.85" />
          <circle cx="18" cy="9" r="1.2" fill="#FFD700" fillOpacity="0.8" />
          <circle cx="12" cy="18" r="1.1" fill="#FFA500" fillOpacity="0.7" />
          <circle cx="20" cy="20" r="0.9" fill="#FFFFFF" fillOpacity="0.6" />
          <circle cx="4" cy="16" r="1" fill="#FFE066" fillOpacity="0.75" />
        </pattern>,
      );
      bodyPatternFill = `url(#${patternId})`;
      endPatternFill = bodyPatternFill;
      patternOpacity = 1;
      break;
    }
    case 'fibers': {
      const patternId = makeId('fibers');
      defs.push(
        <pattern
          id={patternId}
          key={patternId}
          width="6"
          height="6"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <rect width="2" height="6" fill="#6d4c41" fillOpacity="0.6" />
        </pattern>,
      );
      bodyPatternFill = `url(#${patternId})`;
      endPatternFill = bodyPatternFill;
      patternOpacity = 0.55;
      break;
    }
    case 'stone': {
      const patternId = makeId('stone');
      defs.push(
        <pattern id={patternId} key={patternId} width="40" height="40" patternUnits="userSpaceOnUse">
          <rect width="40" height="40" fill="none" />
          <path d="M0 20 Q10 10 20 20 T40 20" stroke="#FFFFFF" strokeOpacity="0.2" strokeWidth="2" fill="none" />
          <path d="M0 30 Q15 24 30 30 T40 30" stroke="#C8C8C8" strokeOpacity="0.2" strokeWidth="3" fill="none" />
          <ellipse cx="12" cy="14" rx="6" ry="3" fill="#FFFFFF" fillOpacity="0.12" />
          <ellipse cx="30" cy="28" rx="8" ry="4" fill="#D0D0D0" fillOpacity="0.12" />
        </pattern>,
      );
      bodyPatternFill = `url(#${patternId})`;
      endPatternFill = bodyPatternFill;
      patternOpacity = 0.7;
      break;
    }
    case 'luminescent': {
      const filterId = makeId('glow');
      defs.push(
        <filter id={filterId} key={filterId} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>,
      );
      glowFilterId = filterId;
      patternOpacity = 0;
      break;
    }
    default: {
      const patternMap: Record<string, [number, number, number]> = {
        pattern1: [-45, 1, 5],
        pattern2: [-45, 1, 3],
        pattern3: [-26, 2, 5],
        pattern4: [0, 1, 3],
        pattern5: [90, 1, 5],
        pattern6: [11, 1, 3],
        pattern7: [-214, 1, 6],
        pattern8: [-319, 1, 4],
        pattern9: [315, 2, 4],
        pattern10: [233, 1, 5],
        pattern11: [223, 1, 9],
        pattern12: [36, 1, 4],
      };
      const config = patternMap[filler];
      if (config) {
        const [angle, width, gap] = config;
        const patternId = makeId(filler);
        defs.push(addStripePattern(patternId, width, gap, angle));
        bodyPatternFill = `url(#${patternId})`;
        endPatternFill = bodyPatternFill;
        patternOpacity = 0.4;
      }
    }
  }

  return { defs, bodyPatternFill, endPatternFill, patternOpacity, glowFilterId };
};

interface FilamentPreviewProps {
  colorHex?: string | null;
  visualSettings?: FilamentVisualSettings | null;
  size?: SizeKey;
  className?: string;
}

export const FilamentPreview: React.FC<FilamentPreviewProps> = ({
  colorHex = '#FFFFFF',
  visualSettings = null,
  size = 'medium',
  className = '',
}) => {
  const svgId = useId().replace(/:/g, '_');
  const config = SIZE_CONFIG[size];
  const radius = config.height / 2;
  const width = config.bodyLength + radius * 2;
  const height = config.height;
  const strokeWidth = config.strokeWidth;
  const canvasPadding = strokeWidth / 2;
  const svgWidth = width + canvasPadding * 2;
  const svgHeight = height + canvasPadding * 2;
  const colors = useMemo(
    () =>
      (visualSettings?.colors?.length ? visualSettings.colors : [colorHex]).map((c) =>
        sanitizeColor(c),
      ),
    [visualSettings?.colors, colorHex],
  );
  const colorType = visualSettings?.color_type || 'single';
  const finish = visualSettings?.finish || 'matte';
  const filler = visualSettings?.filler || 'none';
  const isGlossy = finish === 'glossy';
  const isTransparent = visualSettings?.transparency ?? false;
  const mainColor = colors[0] ?? '#FFFFFF';
  const luminance = getLuminance(mainColor);
  const borderColor = luminance > 0.85 ? '#9CA3AF' : '#FFFFFF';
  const baseHex = colors[0] ?? sanitizeColor(colorHex);
  const bodyLength = config.bodyLength;
  const bodyStart = radius;
  const bodyEnd = radius + bodyLength;
  const centerX = bodyEnd;
  const centerY = radius;

  const { defs: colorDefs, bodyFill, endFill, extraEndSegments } = useMemo(
    () =>
      createColorDefinitions(
        colors,
        colorType,
        svgId,
        baseHex,
        bodyLength,
        bodyStart,
        bodyEnd,
        radius,
      ),
    [colors, colorType, svgId, baseHex, bodyLength, bodyStart, bodyEnd, radius],
  );

  const { defs: fillerDefs, bodyPatternFill, endPatternFill, patternOpacity, glowFilterId } =
    useMemo(() => createFillerDefinitions(filler, colors, svgId), [filler, colors, svgId]);

  const highlightDefs = useMemo(() => {
    if (!isGlossy) {
      return {
        defs: [] as React.ReactNode[],
        bodyHighlightId: null as string | null,
        endHighlightId: null as string | null,
        bodySpecularId: null as string | null,
        endSpecularId: null as string | null,
        bodyShadowId: null as string | null,
        endShadowId: null as string | null,
      };
    }

    const bodyHighlightId = `${svgId}-body-highlight`;
    const endHighlightId = `${svgId}-end-highlight`;
    const bodySpecularId = `${svgId}-body-specular`;
    const endSpecularId = `${svgId}-end-specular`;
    const bodyShadowId = `${svgId}-body-shadow`;
    const endShadowId = `${svgId}-end-shadow`;
    return {
      bodyHighlightId,
      endHighlightId,
      bodySpecularId,
      endSpecularId,
      bodyShadowId,
      endShadowId,
      defs: [
        <linearGradient id={bodyHighlightId} key={bodyHighlightId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.35" />
          <stop offset="42%" stopColor="#FFFFFF" stopOpacity="0.18" />
          <stop offset="65%" stopColor="#FFFFFF" stopOpacity="0.05" />
          <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0" />
        </linearGradient>,
        <radialGradient id={endHighlightId} key={endHighlightId} cx="25%" cy="25%" r="100%">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.35" />
          <stop offset="55%" stopColor="#FFFFFF" stopOpacity="0.12" />
          <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0" />
        </radialGradient>,
        <radialGradient
          id={bodySpecularId}
          key={bodySpecularId}
          cx={bodyEnd - radius * 1.2}
          cy={radius * 0.4}
          r={radius * 1.6}
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.6" />
          <stop offset="45%" stopColor="#FFFFFF" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0" />
        </radialGradient>,
        <radialGradient
          id={endSpecularId}
          key={endSpecularId}
          cx={bodyEnd + radius * 0.35}
          cy={radius * 0.25}
          r={radius * 0.9}
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.6" />
          <stop offset="60%" stopColor="#FFFFFF" stopOpacity="0.2" />
          <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0" />
        </radialGradient>,
        <linearGradient id={bodyShadowId} key={bodyShadowId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#000000" stopOpacity="0" />
          <stop offset="65%" stopColor="#000000" stopOpacity="0" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0.25" />
        </linearGradient>,
        <radialGradient
          id={endShadowId}
          key={endShadowId}
          cx={bodyEnd - radius * 0.1}
          cy={radius * 1.05}
          r={radius * 1.2}
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0%" stopColor="#000000" stopOpacity="0" />
          <stop offset="75%" stopColor="#000000" stopOpacity="0.15" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0.35" />
        </radialGradient>,
      ],
    };
  }, [isGlossy, svgId, bodyEnd, radius]);

  const defs = useMemo(
    () => [...colorDefs, ...fillerDefs, ...highlightDefs.defs],
    [colorDefs, fillerDefs, highlightDefs.defs],
  );

  const bodyPath = useMemo(() => {
    const left = bodyStart;
    const right = bodyEnd;
    const c = radius * 0.5523;
    return [
      `M ${left} 0`,
      `H ${right}`,
      `C ${right + c} 0 ${right + radius} ${radius - c} ${right + radius} ${radius}`,
      `C ${right + radius} ${radius + c} ${right + c} ${height} ${right} ${height}`,
      `H ${left}`,
      `C ${left - c} ${height} ${left - radius} ${radius + c} ${left - radius} ${radius}`,
      `C ${left - radius} ${radius - c} ${left - c} 0 ${left} 0`,
      'Z',
    ].join(' ');
  }, [bodyStart, bodyEnd, radius, height]);

  const bodyFillOpacity = isTransparent ? 0.6 : 1;

  const createEndSegmentPath = (startAngle: number, endAngle: number): string => {
    const startRad = ((startAngle - 90) * Math.PI) / 180;
    const endRad = ((endAngle - 90) * Math.PI) / 180;
    const startX = centerX + radius * Math.cos(startRad);
    const startY = centerY + radius * Math.sin(startRad);
    const endX = centerX + radius * Math.cos(endRad);
    const endY = centerY + radius * Math.sin(endRad);
    const delta =
      ((endAngle - startAngle) % 360 + 360) % 360; // нормализуем диапазон в [0, 360)
    const largeArcFlag = delta > 180 ? 1 : 0;
    const sweepFlag = 1;
    return `M ${centerX} ${centerY} L ${startX} ${startY} A ${radius} ${radius} 0 ${largeArcFlag} ${sweepFlag} ${endX} ${endY} Z`;
  };

  return (
    <div
      className={`relative flex items-center justify-center ${className}`}
      style={{ width: svgWidth + radius, height: svgHeight }}
    >
      <svg
        width={svgWidth}
        height={svgHeight}
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        style={{ overflow: 'visible' }}
      >
        <defs>{defs}</defs>
        <g transform={`translate(${canvasPadding}, ${canvasPadding})`}>
        {isTransparent && (
          <>
              <path
                d={bodyPath}
                fill="none"
                stroke={borderColor}
                strokeWidth={strokeWidth}
                opacity={0.35}
              />
              <circle
                cx={bodyStart}
                cy={radius}
                r={radius}
                fill="none"
                stroke={borderColor}
                strokeWidth={strokeWidth}
                opacity={0.35}
              />
            </>
          )}
          <g filter={glowFilterId ? `url(#${glowFilterId})` : undefined}>
            <path d={bodyPath} fill={bodyFill} fillOpacity={bodyFillOpacity} />
            {bodyPatternFill && patternOpacity > 0 && (
              <path d={bodyPath} fill={bodyPatternFill} fillOpacity={patternOpacity} />
            )}
            {highlightDefs.bodyHighlightId && (
              <path
                d={bodyPath}
                fill={`url(#${highlightDefs.bodyHighlightId})`}
                opacity={isTransparent ? 0.4 : 0.75}
              />
            )}
            {highlightDefs.bodySpecularId && (
              <path
                d={bodyPath}
                fill={`url(#${highlightDefs.bodySpecularId})`}
                opacity={isTransparent ? 0.25 : 0.55}
              />
            )}
            <path d={bodyPath} fill="none" stroke={borderColor} strokeWidth={strokeWidth} />
            <circle
              cx={bodyEnd}
              cy={radius}
              r={radius}
              fill={endFill}
            />
            {extraEndSegments?.map((segment, index) => (
              <path
                key={`segment-${index}`}
                d={createEndSegmentPath(segment.startAngle, segment.endAngle)}
                fill={segment.color}
              />
            ))}
            {endPatternFill && patternOpacity > 0 && (
              <circle
                cx={bodyEnd}
                cy={radius}
                r={radius}
                fill={endPatternFill}
                fillOpacity={patternOpacity}
              />
            )}
            {highlightDefs.endHighlightId && (
              <circle
                cx={bodyEnd}
                cy={radius}
                r={radius}
                fill={`url(#${highlightDefs.endHighlightId})`}
                opacity={isTransparent ? 0.35 : 0.7}
            />
          )}
            {highlightDefs.endSpecularId && (
              <circle
                cx={bodyEnd}
                cy={radius}
                r={radius}
                fill={`url(#${highlightDefs.endSpecularId})`}
                opacity={isTransparent ? 0.15 : 0.4}
              />
            )}
            <circle
              cx={bodyEnd}
              cy={radius}
              r={radius}
              fill="none"
              stroke={borderColor}
              strokeWidth={strokeWidth}
            />
          </g>
        </g>
      </svg>
      {colorType === 'thermochromic' && (
        <div
          className="pointer-events-none absolute flex items-center justify-center"
          style={{
            left: canvasPadding + bodyEnd - radius - strokeWidth / 2,
            width: radius * 3 + strokeWidth
              }}
            >
              <Thermometer
            size={radius}
            color={borderColor}
            strokeWidth={strokeWidth}
              />
        </div>
      )}
    </div>
  );
};
