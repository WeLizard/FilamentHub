/** Компонент цветового пикера со слайдерами HSL в стиле из примера */

import React, { useState, useEffect, useRef } from 'react';

interface HSLColorPickerProps {
  /** HEX цвет */
  color: string;
  /** Callback при изменении цвета */
  onChange: (hex: string) => void;
  /** Показать ли пикер (по умолчанию false) */
  isOpen?: boolean;
  /** Callback при изменении видимости */
  onToggle?: (isOpen: boolean) => void;
}

// Конвертация HEX в HSL
function hexToHsl(hex: string): { h: number; s: number; l: number } {
  // Удаляем # если есть
  const cleanHex = hex.replace('#', '');
  
  // Преобразуем в RGB
  let r = parseInt(cleanHex.substring(0, 2), 16) / 255;
  let g = parseInt(cleanHex.substring(2, 4), 16) / 255;
  let b = parseInt(cleanHex.substring(4, 6), 16) / 255;

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

// Конвертация HSL в HEX
function hslToHex(h: number, s: number, l: number): string {
  h = h / 360;
  s = s / 100;
  l = l / 100;

  let r: number, g: number, b: number;

  if (s === 0) {
    r = g = b = l; // achromatic
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

export const HSLColorPicker: React.FC<HSLColorPickerProps> = ({
  color,
  onChange,
  isOpen: controlledIsOpen,
  onToggle,
}) => {
  const [h, setH] = useState(0);
  const [s, setS] = useState(80);
  const [l, setL] = useState(50);
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const flyoutRef = useRef<HTMLDivElement>(null);
  const isInternalChange = useRef(false); // Флаг для отслеживания внутренних изменений

  // Используем controlled или internal state
  const isOpen = controlledIsOpen !== undefined ? controlledIsOpen : internalIsOpen;

  // Инициализируем HSL из HEX цвета (только если цвет действительно изменился извне)
  useEffect(() => {
    // Если это не внутреннее изменение (из слайдеров), обновляем HSL из пропса color
    if (!isInternalChange.current) {
      try {
        const hsl = hexToHsl(color);
        // Обновляем только если значения отличаются, чтобы избежать лишних рендеров
        setH((prevH) => (Math.abs(prevH - hsl.h) > 0.5 ? hsl.h : prevH));
        setS((prevS) => (Math.abs(prevS - hsl.s) > 0.5 ? hsl.s : prevS));
        setL((prevL) => (Math.abs(prevL - hsl.l) > 0.5 ? hsl.l : prevL));
      } catch (e) {
        // Если цвет невалидный, игнорируем
      }
    }
    // Сбрасываем флаг после обработки
    isInternalChange.current = false;
  }, [color]);

  // Обработчики для слайдеров - напрямую обновляем HEX
  const handleHChange = (newH: number) => {
    setH(newH);
    const newHex = hslToHex(newH, s, l);
    isInternalChange.current = true;
    onChange(newHex);
  };

  const handleSChange = (newS: number) => {
    setS(newS);
    const newHex = hslToHex(h, newS, l);
    isInternalChange.current = true;
    onChange(newHex);
  };

  const handleLChange = (newL: number) => {
    setL(newL);
    const newHex = hslToHex(h, s, newL);
    isInternalChange.current = true;
    onChange(newHex);
  };

  const hide = () => {
    if (onToggle) {
      onToggle(false);
    } else {
      setInternalIsOpen(false);
    }
  };

  // Закрываем при клике вне пикера
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (isOpen && flyoutRef.current) {
        const target = event.target as Node;
        // Проверяем, что клик был не внутри пикера
        if (!flyoutRef.current.contains(target)) {
          // Также проверяем, что это не клик на overlay (overlay сам закроет пикер)
          const overlay = document.querySelector('.fixed.inset-0.z-40.bg-black\\/50');
          if (!overlay?.contains(target)) {
            hide();
          }
        }
      }
    };

    if (isOpen) {
      // Используем capture phase для лучшего отслеживания кликов
      document.addEventListener('mousedown', handleClickOutside, true);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside, true);
    };
  }, [isOpen, hide]);

  const hslColor = `hsl(${h}, ${s}%, ${l}%)`;
  const colorString = `${h}, ${s}%, ${l}%`;

  // Градиенты для слайдеров
  const gradientH = {
    backgroundImage: `linear-gradient(to right, 
      hsl(0, ${s}%, ${l}%),
      hsl(60, ${s}%, ${l}%),
      hsl(120, ${s}%, ${l}%),
      hsl(180, ${s}%, ${l}%),
      hsl(240, ${s}%, ${l}%),
      hsl(300, ${s}%, ${l}%),
      hsl(360, ${s}%, ${l}%)
    )`,
  };

  const gradientS = {
    backgroundImage: `linear-gradient(to right, 
      hsl(${h}, 0%, ${l}%),
      hsl(${h}, 100%, ${l}%)
    )`,
  };

  const gradientL = {
    backgroundImage: `linear-gradient(to right, 
      hsl(${h}, ${s}%, 0%),
      hsl(${h}, ${s}%, 100%)
    )`,
  };

  return (
    <div className="relative">
      {/* Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
          onClick={hide}
          style={{ pointerEvents: 'auto' }}
        />
      )}

      {/* Flyout */}
      <div
        ref={flyoutRef}
        className={`hsl-color-picker-flyout absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-60 bg-gray-900 border border-white/20 rounded-xl shadow-2xl z-[100] transition-all duration-300 ${
          isOpen
            ? 'opacity-100 translate-y-0 scale-100'
            : 'opacity-0 translate-y-2 scale-95 pointer-events-none'
        }`}
      >
        {/* Color chip - уменьшен на 50% по высоте */}
        <div
          className="h-32 flex flex-col justify-center items-center text-white rounded-t-xl"
          style={{ background: hslColor }}
        >
          <div className="text-center">
            <h1 className="text-5xl font-bold tracking-wider mb-2 drop-shadow-lg">HSL</h1>
            <h3 className="text-base opacity-90 drop-shadow">{colorString}</h3>
          </div>
        </div>

        {/* Controls - ползунки поверх цветных полосок */}
        <div className="p-4 space-y-4">
          {/* Hue slider */}
          <div className="w-full h-3 rounded-full border border-white/20 relative flex items-center" style={gradientH}>
            <input
              type="range"
              min="0"
              max="360"
              value={h}
              onChange={(e) => handleHChange(Number(e.target.value))}
              className="w-full h-full appearance-none bg-transparent cursor-pointer slider-thumb z-10"
              style={{ zIndex: 10 }}
            />
          </div>

          {/* Saturation slider */}
          <div className="w-full h-3 rounded-full border border-white/20 relative flex items-center" style={gradientS}>
            <input
              type="range"
              min="0"
              max="100"
              value={s}
              onChange={(e) => handleSChange(Number(e.target.value))}
              className="w-full h-full appearance-none bg-transparent cursor-pointer slider-thumb z-10"
              style={{ zIndex: 10 }}
            />
          </div>

          {/* Lightness slider */}
          <div className="w-full h-3 rounded-full border border-white/20 relative flex items-center" style={gradientL}>
            <input
              type="range"
              min="0"
              max="100"
              value={l}
              onChange={(e) => handleLChange(Number(e.target.value))}
              className="w-full h-full appearance-none bg-transparent cursor-pointer slider-thumb z-10"
              style={{ zIndex: 10 }}
            />
          </div>
        </div>
      </div>

      {/* Swatch не нужен - используем FilamentPreview как триггер */}
    </div>
  );
};

