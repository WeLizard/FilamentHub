import React, { useMemo, useId } from 'react';
import { Thermometer } from 'lucide-react';
import type { FilamentVisualSettings } from '../types/api';
import { sanitizeColor, adjustLightness, getLuminance } from '../utils/color';

type SizeKey = 'small' | 'medium' | 'large';

const SIZE_CONFIG: Record<SizeKey, { height: number; bodyLength: number; strokeWidth: number }> = {
  small: { height: 40, bodyLength: 90, strokeWidth: 2 },
  medium: { height: 60, bodyLength: 120, strokeWidth: 3 },
  large: { height: 90, bodyLength: 200, strokeWidth: 4 },
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
  endPatternOpacity: number;
  glowFilterId: string | null;
};

const createFillerDefinitions = (filler: string, colors: string[], idPrefix: string): FillerDefResult => {
  const defs: React.ReactNode[] = [];
  let bodyPatternFill: string | null = null;
  let endPatternFill: string | null = null;
  let patternOpacity = 0.35;
  let endPatternOpacity = patternOpacity;
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

  const addCutPattern = (
    id: string,
    strokeColor: string,
    fillColor: string,
    opacity = 0.45,
  ) => (
    <pattern id={id} key={id} width="14" height="14" patternUnits="userSpaceOnUse">
      <circle cx="3" cy="3" r="1" fill={fillColor} fillOpacity={opacity} />
      <circle cx="11" cy="9" r="0.8" fill={fillColor} fillOpacity={opacity * 0.8} />
      <path
        d="M7 2 l3 2 M2 10 l3 -1 M8 12 l2 -2"
        stroke={strokeColor}
        strokeWidth="1"
        strokeLinecap="round"
        strokeOpacity={opacity}
      />
    </pattern>
  );

  switch (filler) {
    case 'none':
      return { defs, bodyPatternFill, endPatternFill, patternOpacity, endPatternOpacity, glowFilterId };
    case 'carbon': {
      const patternId = makeId('carbon');
      const endPatternId = makeId('carbon-end');
      defs.push(
        <pattern id={patternId} key={patternId} width="8" height="8" patternUnits="userSpaceOnUse">
          <rect width="8" height="8" fill="#1A1A1A" />
          <path d="M0 0 L8 8 M8 0 L0 8" stroke="#2E2E2E" strokeWidth="1" strokeOpacity="0.6" fill="none" />
          <path d="M0 4 L8 4" stroke="#0F0F0F" strokeWidth="1" strokeOpacity="0.4" />
        </pattern>,
      );
      defs.push(
        <pattern id={endPatternId} key={endPatternId} width="14" height="14" patternUnits="userSpaceOnUse">
          <rect width="14" height="14" fill="#1A1A1A" />
          <circle cx="3" cy="3" r="1" fill="#030712" fillOpacity="0.9" />
          <circle cx="11" cy="9" r="0.8" fill="#030712" fillOpacity="0.75" />
          <path d="M7 2 l3 2 M2 10 l3 -1 M8 12 l2 -2" stroke="#2E2E2E" strokeWidth="1" strokeLinecap="round" />
        </pattern>,
      );
      bodyPatternFill = `url(#${patternId})`;
      endPatternFill = `url(#${endPatternId})`;
      patternOpacity = 0.55;
      endPatternOpacity = 0.92;
      break;
    }
    case 'carbonaceous': {
      const bodyPatternId = makeId('carbonaceous');
      const endPatternId = makeId('carbonaceous-end');
      defs.push(
        <pattern id={bodyPatternId} key={bodyPatternId} width="18" height="14" patternUnits="userSpaceOnUse">
          <rect width="18" height="14" fill="#111827" fillOpacity="0.72" />
          <circle cx="3" cy="4" r="0.65" fill="#000000" fillOpacity="0.7" />
          <circle cx="12" cy="3" r="0.45" fill="#374151" fillOpacity="0.75" />
          <circle cx="8" cy="11" r="0.55" fill="#030712" fillOpacity="0.8" />
          <circle cx="16" cy="9" r="0.4" fill="#4B5563" fillOpacity="0.55" />
        </pattern>,
      );
      defs.push(
        <pattern id={endPatternId} key={endPatternId} width="12" height="12" patternUnits="userSpaceOnUse">
          <rect width="12" height="12" fill="#111827" fillOpacity="0.72" />
          <circle cx="2" cy="3" r="0.7" fill="#000000" fillOpacity="0.78" />
          <circle cx="8" cy="2" r="0.45" fill="#4B5563" fillOpacity="0.62" />
          <circle cx="6" cy="8" r="0.6" fill="#030712" fillOpacity="0.82" />
          <circle cx="11" cy="10" r="0.4" fill="#374151" fillOpacity="0.7" />
        </pattern>,
      );
      bodyPatternFill = `url(#${bodyPatternId})`;
      endPatternFill = `url(#${endPatternId})`;
      patternOpacity = 0.48;
      break;
    }
    case 'glass': {
      const patternId = makeId('glass');
      const endPatternId = makeId('glass-end');
      defs.push(
        <pattern id={patternId} key={patternId} width="19" height="15" patternUnits="userSpaceOnUse">
          <path
            d="M1 3 l8 3 M12 2 l5 2 M4 12 l7 -3 M13 11 l5 2 M1 8 l4 1"
            stroke="#FFFFFF"
            strokeWidth="0.75"
            strokeLinecap="round"
            strokeOpacity="0.48"
          />
          <circle cx="10" cy="4" r="0.7" fill="#FFFFFF" fillOpacity="0.52" />
        </pattern>,
      );
      defs.push(addCutPattern(endPatternId, '#FFFFFF', '#E5E7EB', 0.58));
      bodyPatternFill = `url(#${patternId})`;
      endPatternFill = `url(#${endPatternId})`;
      patternOpacity = 0.72;
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
      const endPatternId = makeId('wood-end');
      const base = sanitizeColor(colors[0] ?? '#9A6B4A');
      const grain = adjustLightness(base, -0.3);
      const grainLight = adjustLightness(base, 0.24);
      defs.push(
        <pattern id={patternId} key={patternId} width="46" height="18" patternUnits="userSpaceOnUse">
          <path
            d="M0 5 C12 2 22 8 46 4 M0 12 C16 7 27 16 46 11"
            fill="none"
            stroke={grain}
            strokeWidth="1.1"
            strokeOpacity="0.58"
          />
          <path
            d="M8 7 C12 4 16 4 20 7 S28 10 32 7"
            fill="none"
            stroke={grainLight}
            strokeWidth="0.55"
            strokeOpacity="0.45"
          />
          <circle cx="37" cy="6" r="1" fill={grain} fillOpacity="0.5" />
        </pattern>,
      );
      defs.push(addCutPattern(endPatternId, grain, grainLight, 0.52));
      bodyPatternFill = `url(#${patternId})`;
      endPatternFill = `url(#${endPatternId})`;
      patternOpacity = 0.72;
      break;
    }
    case 'microspheres': {
      const bodyPatternId = makeId('microspheres');
      const endPatternId = makeId('microspheres-end');
      defs.push(
        <pattern id={bodyPatternId} key={bodyPatternId} width="22" height="18" patternUnits="userSpaceOnUse">
          <circle cx="4" cy="5" r="1.5" fill="none" stroke="#FFFFFF" strokeWidth="0.7" strokeOpacity="0.58" />
          <circle cx="15" cy="4" r="1" fill="#FFFFFF" fillOpacity="0.28" />
          <circle cx="10" cy="14" r="1.8" fill="none" stroke="#E5E7EB" strokeWidth="0.65" strokeOpacity="0.52" />
          <circle cx="20" cy="12" r="0.8" fill="#FFFFFF" fillOpacity="0.36" />
        </pattern>,
      );
      defs.push(
        <pattern id={endPatternId} key={endPatternId} width="16" height="16" patternUnits="userSpaceOnUse">
          <circle cx="3" cy="4" r="1.6" fill="none" stroke="#FFFFFF" strokeWidth="0.7" strokeOpacity="0.65" />
          <circle cx="11" cy="3" r="1" fill="#FFFFFF" fillOpacity="0.34" />
          <circle cx="8" cy="11" r="1.9" fill="none" stroke="#E5E7EB" strokeWidth="0.65" strokeOpacity="0.58" />
          <circle cx="15" cy="13" r="0.8" fill="#FFFFFF" fillOpacity="0.42" />
        </pattern>,
      );
      bodyPatternFill = `url(#${bodyPatternId})`;
      endPatternFill = `url(#${endPatternId})`;
      patternOpacity = 0.72;
      break;
    }
    case 'particles': {
      const bodyPatternId = makeId('particles');
      const endPatternId = makeId('particles-end');
      defs.push(
        <pattern id={bodyPatternId} key={bodyPatternId} width="20" height="16" patternUnits="userSpaceOnUse">
          <circle cx="3" cy="4" r="0.9" fill="#FFFFFF" fillOpacity="0.5" />
          <circle cx="12" cy="3" r="0.55" fill="#F3F4F6" fillOpacity="0.38" />
          <circle cx="8" cy="12" r="0.75" fill="#FFFFFF" fillOpacity="0.46" />
          <circle cx="18" cy="10" r="0.45" fill="#D1D5DB" fillOpacity="0.42" />
        </pattern>,
      );
      defs.push(addCutPattern(endPatternId, '#F9FAFB', '#FFFFFF', 0.5));
      bodyPatternFill = `url(#${bodyPatternId})`;
      endPatternFill = `url(#${endPatternId})`;
      patternOpacity = 0.6;
      break;
    }
    case 'glitter': {
      const patternId = makeId('glitter');
      const endPatternId = makeId('glitter-end');
      defs.push(
        <pattern id={patternId} key={patternId} width="30" height="25" patternUnits="userSpaceOnUse">
          <path d="M5 3 l1.4 2.5 L5 8 l-1.4 -2.5 Z" fill="#FFFFFF" fillOpacity="0.9" />
          <path d="M21 5 l2 1 l-1 2 l-2 -1 Z" fill="#FFD700" fillOpacity="0.86" />
          <path d="M13 18 l1.2 2.2 l-1.2 2.2 l-1.2 -2.2 Z" fill="#FFA500" fillOpacity="0.78" />
          <circle cx="27" cy="18" r="0.8" fill="#FFFFFF" fillOpacity="0.65" />
        </pattern>,
      );
      defs.push(
        <pattern id={endPatternId} key={endPatternId} width="22" height="22" patternUnits="userSpaceOnUse">
          <path d="M4 5 l1.2 2 L4 9 l-1.2 -2 Z" fill="#FFFFFF" fillOpacity="0.88" />
          <path d="M15 3 l2 1 l-1 2 l-2 -1 Z" fill="#FFD700" fillOpacity="0.82" />
          <path d="M11 15 l1.2 2 l-1.2 2 l-1.2 -2 Z" fill="#FFA500" fillOpacity="0.74" />
          <circle cx="19" cy="16" r="0.7" fill="#FFFFFF" fillOpacity="0.58" />
        </pattern>,
      );
      bodyPatternFill = `url(#${patternId})`;
      endPatternFill = `url(#${endPatternId})`;
      patternOpacity = 1;
      break;
    }
    case 'fibers': {
      const patternId = makeId('fibers');
      const endPatternId = makeId('fibers-end');
      defs.push(
        <pattern id={patternId} key={patternId} width="26" height="21" patternUnits="userSpaceOnUse">
          <path
            d="M2 5 l10 3 M15 3 l8 5 M5 17 l12 -4 M19 17 l5 2 M1 12 l6 -1"
            stroke="#4B5563"
            strokeWidth="1.35"
            strokeLinecap="round"
            strokeOpacity="0.72"
          />
          <path d="M9 2 l4 2 M14 19 l5 -2" stroke="#FFFFFF" strokeWidth="0.7" strokeOpacity="0.28" />
        </pattern>,
      );
      defs.push(addCutPattern(endPatternId, '#4B5563', '#D1D5DB', 0.64));
      bodyPatternFill = `url(#${patternId})`;
      endPatternFill = `url(#${endPatternId})`;
      patternOpacity = 0.72;
      break;
    }
    case 'stone': {
      const patternId = makeId('stone');
      const endPatternId = makeId('stone-end');
      defs.push(
        <pattern id={patternId} key={patternId} width="28" height="24" patternUnits="userSpaceOnUse">
          <circle cx="4" cy="5" r="1.4" fill="#111827" fillOpacity="0.62" />
          <circle cx="17" cy="4" r="0.8" fill="#FFFFFF" fillOpacity="0.42" />
          <circle cx="9" cy="16" r="1" fill="#9CA3AF" fillOpacity="0.48" />
          <circle cx="23" cy="14" r="1.8" fill="#030712" fillOpacity="0.45" />
          <path d="M18 20 l3 1 M2 21 l2 -1 M25 6 l2 1" stroke="#FFFFFF" strokeWidth="0.7" strokeOpacity="0.38" />
        </pattern>,
      );
      defs.push(
        <pattern id={endPatternId} key={endPatternId} width="20" height="20" patternUnits="userSpaceOnUse">
          <circle cx="3" cy="4" r="1" fill="#111827" fillOpacity="0.6" />
          <circle cx="13" cy="3" r="1.4" fill="#FFFFFF" fillOpacity="0.35" />
          <circle cx="8" cy="13" r="1.7" fill="#030712" fillOpacity="0.42" />
          <circle cx="17" cy="14" r="0.8" fill="#D1D5DB" fillOpacity="0.5" />
        </pattern>,
      );
      bodyPatternFill = `url(#${patternId})`;
      endPatternFill = `url(#${endPatternId})`;
      patternOpacity = 0.72;
      break;
    }
    case 'luminescent': {
      const filterId = makeId('glow');
      const bodyGradientId = makeId('luminescent-body');
      const endGradientId = makeId('luminescent-end');
      defs.push(
        <filter id={filterId} key={filterId} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>,
      );
      defs.push(
        <linearGradient id={bodyGradientId} key={bodyGradientId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.34" />
          <stop offset="42%" stopColor={colors[0] ?? '#C7FF90'} stopOpacity="0.85" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0.18" />
        </linearGradient>,
      );
      defs.push(
        <radialGradient id={endGradientId} key={endGradientId} cx="42%" cy="38%" r="72%">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.5" />
          <stop offset="48%" stopColor={colors[0] ?? '#C7FF90'} stopOpacity="0.9" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0.2" />
        </radialGradient>,
      );
      bodyPatternFill = `url(#${bodyGradientId})`;
      endPatternFill = `url(#${endGradientId})`;
      glowFilterId = filterId;
      patternOpacity = 0.78;
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
        const endPatternId = makeId(`${filler}-end`);
        defs.push(addStripePattern(patternId, width, gap, angle));
        defs.push(addCutPattern(endPatternId, '#FFFFFF', '#D1D5DB', 0.42));
        bodyPatternFill = `url(#${patternId})`;
        endPatternFill = `url(#${endPatternId})`;
        patternOpacity = 0.4;
      }
    }
  }

  if (endPatternOpacity === 0.35) endPatternOpacity = patternOpacity;
  return { defs, bodyPatternFill, endPatternFill, patternOpacity, endPatternOpacity, glowFilterId };
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
  const effects = useMemo(() => {
    const source = visualSettings?.effects?.length
      ? visualSettings.effects
      : (filler !== 'none' ? [filler] : []);
    const layerOrder: Record<string, number> = {
      metallic: 10,
      carbon: 20,
      carbonaceous: 20,
      glass: 20,
      microspheres: 20,
      particles: 20,
      fibers: 20,
      wood: 20,
      stone: 20,
      luminescent: 30,
      glitter: 40,
    };
    return [...new Set(source)].sort((left, right) => (layerOrder[left] ?? 25) - (layerOrder[right] ?? 25));
  }, [visualSettings?.effects, filler]);
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

  const fillerLayers = useMemo(
    () => effects.map((effect, index) => createFillerDefinitions(
      effect,
      colors,
      effects.length === 1 ? svgId : `${svgId}-effect-${index}`,
    )),
    [effects, colors, svgId],
  );
  const fillerDefs = useMemo(() => fillerLayers.flatMap(layer => layer.defs), [fillerLayers]);
  const glowFilterId = fillerLayers.find(layer => layer.glowFilterId)?.glowFilterId ?? null;

  const highlightDefs = useMemo(() => {
    if (!isGlossy) {
      return {
        defs: [] as React.ReactNode[],
        bodyHighlightId: null as string | null,
        endHighlightId: null as string | null,
        bodyShadowId: null as string | null,
        endShadowId: null as string | null,
        bodySoftnessId: null as string | null,
        endSoftnessId: null as string | null,
        bodyGlossClipId: null as string | null,
        endGlossClipId: null as string | null,
      };
    }

    const bodyHighlightId = `${svgId}-body-highlight`;
    const endHighlightId = `${svgId}-end-highlight`;
    const bodyShadowId = `${svgId}-body-shadow`;
    const endShadowId = `${svgId}-end-shadow`;
    const bodySoftnessId = `${svgId}-body-softness`;
    const endSoftnessId = `${svgId}-end-softness`;
    const bodyGlossClipId = `${svgId}-body-gloss-clip`;
    const endGlossClipId = `${svgId}-end-gloss-clip`;
    return {
      bodyHighlightId,
      endHighlightId,
      bodyShadowId,
      endShadowId,
      bodySoftnessId,
      endSoftnessId,
      bodyGlossClipId,
      endGlossClipId,
      defs: [
        <linearGradient id={bodyHighlightId} key={bodyHighlightId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.48" />
          <stop offset="42%" stopColor="#FFFFFF" stopOpacity="0.18" />
          <stop offset="72%" stopColor="#FFFFFF" stopOpacity="0" />
          <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0" />
        </linearGradient>,
        <radialGradient id={endHighlightId} key={endHighlightId} cx="28%" cy="24%" r="90%">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.55" />
          <stop offset="55%" stopColor="#FFFFFF" stopOpacity="0.12" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0.24" />
        </radialGradient>,
        <linearGradient id={bodyShadowId} key={bodyShadowId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#000000" stopOpacity="0" />
          <stop offset="58%" stopColor="#000000" stopOpacity="0" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0.28" />
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
        <filter id={bodySoftnessId} key={bodySoftnessId} x="-20%" y="-35%" width="140%" height="170%">
          <feGaussianBlur stdDeviation={radius * 0.1} />
        </filter>,
        <filter id={endSoftnessId} key={endSoftnessId} x="-35%" y="-35%" width="170%" height="170%">
          <feGaussianBlur stdDeviation={radius * 0.1} />
        </filter>,
        <clipPath id={bodyGlossClipId} key={bodyGlossClipId}>
          <rect x="0" y="0" width={bodyEnd + radius} height={height} rx={radius} />
        </clipPath>,
        <clipPath id={endGlossClipId} key={endGlossClipId}>
          <circle cx={bodyEnd} cy={radius} r={radius} />
        </clipPath>,
      ],
    };
  }, [isGlossy, svgId, bodyEnd, radius, height]);

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
            {fillerLayers.map((layer, index) => layer.bodyPatternFill && layer.patternOpacity > 0 ? (
              <path
                key={`body-effect-${index}`}
                d={bodyPath}
                fill={layer.bodyPatternFill}
                fillOpacity={layer.patternOpacity}
              />
            ) : null)}
            {highlightDefs.bodyShadowId && (
              <path
                d={bodyPath}
                fill={`url(#${highlightDefs.bodyShadowId})`}
                opacity={isTransparent ? 0.35 : 0.9}
              />
            )}
            {highlightDefs.bodyHighlightId && (
              <g clipPath={highlightDefs.bodyGlossClipId ? `url(#${highlightDefs.bodyGlossClipId})` : undefined}>
                <path
                  d={bodyPath}
                  fill={`url(#${highlightDefs.bodyHighlightId})`}
                  opacity={isTransparent ? 0.45 : 0.8}
                  filter={highlightDefs.bodySoftnessId ? `url(#${highlightDefs.bodySoftnessId})` : undefined}
                />
              </g>
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
            {fillerLayers.map((layer, index) => layer.endPatternFill && layer.endPatternOpacity > 0 ? (
              <circle
                key={`end-effect-${index}`}
                cx={bodyEnd}
                cy={radius}
                r={radius}
                fill={layer.endPatternFill}
                fillOpacity={layer.endPatternOpacity}
              />
            ) : null)}
            {highlightDefs.endShadowId && (
              <circle
                cx={bodyEnd}
                cy={radius}
                r={radius}
                fill={`url(#${highlightDefs.endShadowId})`}
                opacity={isTransparent ? 0.3 : 0.8}
              />
            )}
            {highlightDefs.endHighlightId && (
              <g clipPath={highlightDefs.endGlossClipId ? `url(#${highlightDefs.endGlossClipId})` : undefined}>
                <circle
                  cx={bodyEnd}
                  cy={radius}
                  r={radius}
                  fill={`url(#${highlightDefs.endHighlightId})`}
                  opacity={isTransparent ? 0.45 : 0.8}
                  filter={highlightDefs.endSoftnessId ? `url(#${highlightDefs.endSoftnessId})` : undefined}
                />
              </g>
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
