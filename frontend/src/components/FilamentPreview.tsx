/** Компонент визуального превью прутка филамента с поддержкой расширенных эффектов */

import React from 'react';
import { Thermometer } from 'lucide-react';
import type { FilamentVisualSettings } from '../types/api';

interface FilamentPreviewProps {
  colorHex?: string | null;
  visualSettings?: FilamentVisualSettings | null;
  size?: 'small' | 'medium' | 'large';
  className?: string;
}

export const FilamentPreview: React.FC<FilamentPreviewProps> = ({
  colorHex = '#FFFFFF',
  visualSettings = null,
  size = 'medium',
  className = '',
}) => {
  // Размеры в зависимости от пропса size - без отрицательных margin (используем flexbox)
  const sizes = {
    small: { height: 36, rodWidth: 80, rodHeight: 36, endSize: 36, borderRadius: 18 },
    medium: { height: 60, rodWidth: 150, rodHeight: 60, endSize: 60, borderRadius: 30 }, // rodWidth увеличен до 150px
    large: { height: 90, rodWidth: 180, rodHeight: 90, endSize: 90, borderRadius: 45 },
  };

  const { height, rodWidth, rodHeight, endSize, borderRadius } = sizes[size];
  const borderWidth = size === 'small' ? 2 : 3; // Толщина рамки зависит от размера
  
  // Нормализация цвета
  const normalizeColor = (color: string): string => {
    const hex = color.replace('#', '').toUpperCase();
    if (hex.length === 3) {
      return hex.split('').map(c => c + c).join('');
    }
    return hex;
  };

  // Получение цветов для рендеринга
  const getColors = (): string[] => {
    if (visualSettings?.colors && visualSettings.colors.length > 0) {
      return visualSettings.colors;
    }
    return [colorHex || '#FFFFFF'];
  };

  const colors = getColors();
  const color1 = colors[0] || '#FFFFFF';
  
  // Парсим RGB для определения яркости
  const hexColor = normalizeColor(color1);
  const r = parseInt(hexColor.substring(0, 2), 16);
  const g = parseInt(hexColor.substring(2, 4), 16);
  const b = parseInt(hexColor.substring(4, 6), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  const borderColor = luminance > 0.85 ? '#9CA3AF' : '#FFFFFF';

  // Получаем тип цвета
  const colorType = visualSettings?.color_type || 'single';
  
  // Получаем финиш
  const finish = visualSettings?.finish || 'matte';
  const isGlossy = finish === 'glossy';
  
  // Получаем наполнитель
  const filler = visualSettings?.filler || 'none';
  
  // Получаем прозрачность (теперь boolean)
  const isTransparent = visualSettings?.transparency ?? false;
  const opacity = isTransparent ? 0.5 : 1.0; // Полупрозрачный если true

  // Вычисляем background для rod-body
  const getRodBodyBackground = (): string => {
    const baseColors = colors.map(c => c || '#FFFFFF');
    
    if (colorType === 'single') {
      return baseColors[0];
    } else if (colorType === 'two') {
      const c1 = baseColors[0];
      const c2 = baseColors[1] || c1;
      return `linear-gradient(to top, ${c1} 50%, ${c2} 50%)`; // Горизонтальный градиент для длинного прутка (слева направо)
    } else if (colorType === 'three') {
      const c1 = baseColors[0];
      const c2 = baseColors[1] || c1;
      const c3 = baseColors[2] || c2;
      // Для трёхцветного типа при виде сбоку на цилиндр видны только 2 цвета:
      // верхняя часть (видна сверху) = третий цвет (c3)
      // нижняя часть (видна снизу) = второй цвет (c2)
      // Первый цвет (c1) находится в центре цилиндра и не виден сбоку
      // Показываем только верхнюю и нижнюю трети, среднюю скрываем (используем тот же цвет, что и верх/низ)
      return `linear-gradient(to bottom, ${c3} 0%, ${c3} 33.3%, ${c3} 33.3%, ${c3} 76.6%, ${c2} 76.6%, ${c2} 100%)`;
    } else if (colorType === 'gradient') {
      // Многоцветный градиент — используем до 5 цветов
      // Используем радиальный градиент с концентрическими кругами, центрированный на кружке справа (Rod End)
      // Эффект: большой круг (снаружи) -> поменьше -> ещё меньше -> самый маленький (у центра справа)
      // Всё это ограничено прямоугольной формой прутка
      const steps: string[] = [];
      // Распределяем цвета от центра (справа) к краю (слева)
      // Первый цвет - самый внешний (левый край), последний - самый внутренний (у кружка справа)
      for (let i = 0; i < baseColors.length; i++) {
        const percent = (i / (baseColors.length - 1)) * 100;
        steps.push(`${baseColors[baseColors.length - 1 - i]} ${percent}%`);
      }
      // Радиальный градиент с центром справа, создающий концентрические круги
      // Размер градиента достаточно большой, чтобы покрыть всю ширину прутка
      return `radial-gradient(circle at right center, ${steps.join(', ')})`;
    } else if (colorType === 'transition') {
      // Переходной цвет — используем только 2 цвета для плавного перехода
      // Берём только первые 2 цвета, игнорируем остальные
      const c1 = baseColors[0];
      const c2 = baseColors[1] || baseColors[0] || '#FFFFFF';
      // Радиальный градиент с концентрическими кругами, центрированный на кружке справа (Rod End)
      // Первый цвет (c1) в центре справа (где кружок), радиальный градиент во второй цвет (c2) слева
      return `radial-gradient(circle at right center, ${c1} 0%, ${c2} 100%)`;
    } else if (colorType === 'thermochromic') {
      // Термохромный — аналогично transition (меняет цвет при нагреве)
      // Используем только 2 цвета для плавного перехода
      const c1 = baseColors[0];
      const c2 = baseColors[1] || baseColors[0] || '#FFFFFF';
      // Радиальный градиент с концентрическими кругами, центрированный на кружке справа (Rod End)
      return `radial-gradient(circle at right center, ${c1} 0%, ${c2} 100%)`;
    }
    return baseColors[0];
  };

  // Вычисляем background для rod-end
  const getRodEndBackground = (): string => {
    const baseColors = colors.map(c => c || '#FFFFFF');
    
    if (colorType === 'single') {
      return baseColors[0];
    } else if (colorType === 'two') {
      const c1 = baseColors[0];
      const c2 = baseColors[1] || c1;
      return `conic-gradient(from 90deg, ${c1} 0% 50%, ${c2} 50% 100%)`; // Повернуто на 90 градусов (from 90deg вместо from 0deg)
    } else if (colorType === 'three') {
      const c1 = baseColors[0];
      const c2 = baseColors[1] || c1;
      const c3 = baseColors[2] || c2;
      return `conic-gradient(from 0deg, ${c1} 0% 33.3%, ${c2} 33.3% 66.6%, ${c3} 66.6% 100%)`;
    } else if (colorType === 'gradient') {
      // Для градиента используем последний цвет на конце
      return baseColors[baseColors.length - 1] || baseColors[0];
    } else if (colorType === 'transition') {
      // Переходной цвет — используем первый цвет (центр справа, где кружок)
      return baseColors[0];
    } else if (colorType === 'thermochromic') {
      // Термохромный — используем первый цвет (центр справа, где кружок)
      return baseColors[0];
    }
    return baseColors[0];
  };

  // Получаем стили для наполнителя
  const getFillerStyles = (elementType: 'body' | 'end' = 'body'): React.CSSProperties => {
    if (filler === 'none') {
      return {};
    }

    // Получаем цвет для цветного металлика (используем первый цвет из массива)
    const baseColor = colors[0] || '#808080';
    
    // Конвертируем HEX в RGB для манипуляций с яркостью
    const hexToRgb = (hex: string): [number, number, number] => {
      const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
      return result 
        ? [parseInt(result[1], 16), parseInt(result[2], 16), parseInt(result[3], 16)]
        : [128, 128, 128];
    };
    
    const [r, g, b] = hexToRgb(baseColor);
    
    // Создаём оттенки металлика на основе базового цвета (смещение бликов)
    const dark = `rgb(${Math.max(0, r - 60)}, ${Math.max(0, g - 60)}, ${Math.max(0, b - 60)})`;
    const light = `rgb(${Math.min(255, r + 80)}, ${Math.min(255, g + 80)}, ${Math.min(255, b + 80)})`;
    const mediumDark = `rgb(${Math.max(0, r - 30)}, ${Math.max(0, g - 30)}, ${Math.max(0, b - 30)})`;
    const mediumLight = `rgb(${Math.min(255, r + 40)}, ${Math.min(255, g + 40)}, ${Math.min(255, b + 40)})`;
    const baseRgb = `rgb(${r}, ${g}, ${b})`;

    // Для дерева разные стили для Rod Body и Rod End
    if (filler === 'wood') {
      if (elementType === 'end') {
        // Для Rod End (кружок) - радиальный градиент
        return {
          background: `
            radial-gradient(circle at center, #d7ccc8, #bcaaa4 50%, #a1887f 100%)
          `,
        };
      } else {
        // Для Rod Body (длинный пруток) - поворот на 90 градусов (to bottom вместо to right)
        return {
          background: `
            repeating-linear-gradient(to bottom, #d7ccc8, #d7ccc8 4px, #bcaaa4 4px, #bcaaa4 8px),
            linear-gradient(to right, #d7ccc8, #a1887f)
          `,
        };
      }
    }

    // Для металлика разные стили для Rod Body и Rod End
    if (filler === 'metallic') {
      if (elementType === 'end') {
        // Для Rod End (кружок) - радиальный градиент с бликами (смещёнными)
        return {
          background: `radial-gradient(circle at 30% 30%, ${light} 0%, ${mediumLight} 25%, ${baseRgb} 40%, ${mediumDark} 60%, ${dark} 100%)`,
        };
      } else {
        // Для Rod Body (длинный пруток) - поворот на 90 градусов (to bottom) с правильными бликами
        return {
          background: `linear-gradient(to bottom, ${dark} 0%, ${mediumDark} 20%, ${light} 40%, ${mediumLight} 50%, ${light} 60%, ${mediumDark} 80%, ${dark} 100%)`,
        };
      }
    }

    // Для CF (Carbon Fiber) - реалистичная текстура углеродного волокна
    // Обычно чёрный матовый с характерной текстурой плетения
    if (filler === 'carbon') {
      if (elementType === 'end') {
        // Для Rod End (кружок) - радиальный градиент с текстурой плетения
        return {
          background: `
            repeating-conic-gradient(from 0deg, #1a1a1a 0deg 10deg, #2e2e2e 10deg 20deg),
            radial-gradient(circle at center, #2e2e2e 0%, #1a1a1a 100%)
          `,
          backgroundSize: '8px 8px, 100% 100%',
        };
      } else {
        // Для Rod Body (длинный пруток) - текстура плетения углеродного волокна (твил, 2x2)
        return {
          background: `
            repeating-linear-gradient(45deg, #1a1a1a 0px, #1a1a1a 2px, #2e2e2e 2px, #2e2e2e 4px),
            repeating-linear-gradient(-45deg, #2e2e2e 0px, #2e2e2e 2px, #1a1a1a 2px, #1a1a1a 4px),
            repeating-linear-gradient(to bottom, #1f1f1f 0px, #1f1f1f 1px, #2e2e2e 1px, #2e2e2e 2px)
          `,
          backgroundSize: '4px 4px, 4px 4px, 100% 2px',
        };
      }
    }

    // Для GF (Glass Fiber) - используем паттерн 3 с цветом из visualSettings
    // Доступны цвета: чёрный, белый, серый, красный, синий, зелёный, жёлтый, оранжевый, фиолетовый
    // Цвет материала находится в rodBodyBg/rodEndBg, паттерн накладывается поверх как текстура
    if (filler === 'glass') {
      // Используем паттерн 3 для стекловолокна
      // Паттерн 3: repeating-linear-gradient(-26deg, ...) с белым цветом для видимости текстуры
      // Цвет материала уже установлен в rodBodyBg/rodEndBg, поэтому паттерн накладывается поверх
      return {
        backgroundImage: 'repeating-linear-gradient(-26deg, rgba(255,255,255, 0.3), rgba(255,255,255, 0.3) 2px, transparent 3px, transparent 7px)',
        backgroundSize: '6px 8px',
        backgroundBlendMode: 'overlay', // Смешиваем паттерн с цветом материала
      };
    }

    const fillerTextures: Record<string, React.CSSProperties> = {
      // CF и GF обрабатываются отдельно выше
      glitter: {
        background: `
          radial-gradient(circle at 15% 25%, rgba(255,255,255,0.9) 2px, transparent 2px),
          radial-gradient(circle at 85% 75%, rgba(255,215,0,0.8) 2px, transparent 2px),
          radial-gradient(circle at 45% 15%, rgba(255,255,255,0.7) 1.5px, transparent 1.5px),
          radial-gradient(circle at 75% 45%, rgba(255,255,200,0.6) 2px, transparent 2px),
          radial-gradient(circle at 25% 65%, rgba(255,255,255,0.8) 1.5px, transparent 1.5px),
          radial-gradient(circle at 55% 85%, rgba(255,220,100,0.7) 2px, transparent 2px),
          radial-gradient(circle at 90% 30%, rgba(255,255,255,0.6) 1.5px, transparent 1.5px),
          radial-gradient(circle at 35% 80%, rgba(255,215,50,0.7) 2px, transparent 2px)
        `,
        backgroundSize: '25px 25px, 28px 28px, 22px 22px, 26px 26px, 24px 24px, 27px 27px, 23px 23px, 25px 25px',
      },
      luminescent: {
        // Люминофор не имеет текстуры - используется свечение границы вместо этого
        background: 'transparent',
      },
      fibers: {
        background: 'repeating-linear-gradient(45deg, #8d6e63, #8d6e63 1px, #6d4c41 1px, #6d4c41 3px)',
      },
      stone: {
        // Мрамор - волнистые прожилки с плавными переходами
        background: `
          repeating-linear-gradient(75deg, rgba(255,255,255,0.4) 0px, rgba(255,255,255,0.4) 2px, rgba(200,200,200,0.3) 2px, rgba(200,200,200,0.3) 4px, rgba(180,180,180,0.2) 4px, rgba(180,180,180,0.2) 6px, transparent 6px, transparent 15px),
          repeating-linear-gradient(-15deg, rgba(220,220,220,0.3) 0px, rgba(220,220,220,0.3) 3px, rgba(160,160,160,0.25) 3px, rgba(160,160,160,0.25) 5px, transparent 5px, transparent 12px),
          radial-gradient(ellipse at 30% 40%, rgba(255,255,255,0.5) 0%, transparent 50%),
          radial-gradient(ellipse at 70% 60%, rgba(200,200,200,0.4) 0%, transparent 50%),
          linear-gradient(to bottom, rgba(240,240,240,0.8), rgba(200,200,200,0.6))
        `,
        backgroundSize: '40px 60px, 35px 50px, 100px 80px, 120px 100px, 100% 100%',
      },
      glass: {
        background: 'repeating-linear-gradient(to right, #b3e5fc, #b3e5fc 2px, #81d4fa 2px, #81d4fa 4px)',
      },
      pattern1: {
        backgroundImage: 'repeating-linear-gradient(-45deg, rgba(255,255,255, 0.25), rgba(255,255,255, 0.25) 1px, transparent 1px, transparent 6px)',
        backgroundSize: '8px 8px',
      },
      pattern2: {
        backgroundImage: 'repeating-linear-gradient(-45deg, rgba(255,255,255, 0.25), rgba(255,255,255, 0.25) 1px, transparent 1px, transparent 6px)',
        backgroundSize: '4px 4px',
      },
      pattern3: {
        backgroundImage: 'repeating-linear-gradient(-26deg, rgba(255,255,255, 0.25), rgba(255,255,255, 0.25) 2px, transparent 3px, transparent 7px)',
        backgroundSize: '6px 8px',
      },
      pattern4: {
        backgroundImage: 'repeating-linear-gradient(0deg, rgba(255,255,255, 0.25), rgba(255,255,255, 0.25) 1px, transparent 1px, transparent 7px)',
        backgroundSize: '2px 2px',
      },
      pattern5: {
        backgroundImage: 'repeating-linear-gradient(90deg, rgba(255,255,255, 0.25), rgba(255,255,255, 0.25) 1px, transparent 1px, transparent 7px)',
        backgroundSize: '16px 16px',
      },
      pattern6: {
        backgroundImage: 'repeating-linear-gradient(11deg, rgba(255,255,255, 0.25), rgba(255,255,255, 0.25) 1px, transparent 0px, transparent 4px)',
        backgroundSize: '8px 8px',
      },
      pattern7: {
        backgroundImage: 'repeating-linear-gradient(-214deg, rgba(255,255,255, 0.25), rgba(255,255,255, 0.25) 1px, transparent 0px, transparent 13px)',
        backgroundSize: '9px 9px',
      },
      pattern8: {
        backgroundImage: 'repeating-linear-gradient(-319deg, rgba(255,255,255, 0.25), rgba(255,255,255, 0.25) 1px, transparent 3px, transparent 15px)',
        backgroundSize: '4px 4px',
      },
      pattern9: {
        backgroundImage: 'repeating-linear-gradient(315deg, rgba(255,255,255, 0.25), rgba(255,255,255, 0.25) 3px, transparent -19px, transparent 5px)',
        backgroundSize: '6px 6px',
      },
      pattern10: {
        backgroundImage: 'repeating-linear-gradient(233deg, rgba(255,255,255, 0.25), rgba(255,255,255, 0.25) 1px, transparent -19px, transparent 2px)',
        backgroundSize: '10px 10px',
      },
      pattern11: {
        backgroundImage: 'repeating-linear-gradient(223deg, rgba(255,255,255, 0.25), rgba(255,255,255, 0.25) 1px, transparent 0px, transparent 2px)',
        backgroundSize: '20px 20px',
      },
      pattern12: {
        backgroundImage: 'repeating-linear-gradient(36deg, rgba(255,255,255, 0.25), rgba(255,255,255, 0.25) 1px, transparent 0px, transparent 2px)',
        backgroundSize: '12px 12px',
      },
    };

    return fillerTextures[filler] || {};
  };

  const rodBodyBg = getRodBodyBackground();
  const rodEndBg = getRodEndBackground();
  const fillerStylesBody = getFillerStyles('body');
  const fillerStylesEnd = getFillerStyles('end');

  // Вычисляем общую ширину для контейнера
  // Для medium: Rod End смещен на -60px (влево), перекрывает Rod Body больше, поэтому общая ширина = rodWidth - 60 + endSize
  // Для других размеров: Rod End перекрывает Rod Body на половину, поэтому = rodWidth + endSize/2
  const totalWidth = size === 'medium' 
    ? rodWidth - 60 + endSize 
    : rodWidth + endSize / 2;

  return (
    <div className={`flex items-center ${isGlossy ? 'glossy' : ''} ${className}`} style={{ width: `${totalWidth}px`, height: `${height}px`, overflow: 'visible' }}>
      {/* Контейнер filament-rod - используем flexbox вместо абсолютного позиционирования */}
      <div
        className="relative flex items-center"
        style={{
          width: `${totalWidth}px`,
          height: `${height}px`,
        }}
      >
        {/* Задняя обводка для прозрачного материала - создаёт эффект глубины цилиндра */}
        {isTransparent && (
          <>
            {/* Задняя обводка Rod Body - выровнена по левому краю цилиндра */}
            <div
              className="absolute"
              style={{
                width: `${rodWidth}px`,
                height: `${rodHeight}px`,
                borderRadius: `${borderRadius}px`,
                border: `${borderWidth}px solid ${borderColor}`,
                left: 0, // Выровнена по левому краю контейнера
                background: 'transparent',
                zIndex: 0,
              }}
            />
            {/* Задняя обводка Rod End - выровнена по левому краю */}
            <div
              className="absolute rounded-full"
              style={{
                width: `${endSize}px`,
                height: `${endSize}px`,
                border: `${borderWidth}px solid ${borderColor}`,
                left: 0, // Выровнена по левому краю контейнера
                background: 'transparent',
                zIndex: 0,
              }}
            />
          </>
        )}
        
        {/* Rod Body - основная цилиндрическая часть */}
        <div
          className="relative overflow-hidden flex-shrink-0"
          style={{
            width: `${rodWidth}px`,
            height: `${rodHeight}px`,
            background: rodBodyBg,
            borderRadius: `${borderRadius}px`,
            border: `${borderWidth}px solid ${borderColor}`,
            opacity: opacity < 1 ? opacity : undefined,
            zIndex: 1,
            // Добавляем радиальный градиент для объема цилиндра (светлая полоса сверху)
            boxShadow: isTransparent 
              ? 'none' 
              : filler === 'luminescent'
              ? `inset 0 ${-rodHeight * 0.15}px ${rodHeight * 0.3}px -${rodHeight * 0.15}px rgba(255,255,255,0.2), 0 0 10px ${colors[0] || '#FFEB3B'}40, 0 0 20px ${colors[0] || '#FFEB3B'}30`
              : `inset 0 ${-rodHeight * 0.15}px ${rodHeight * 0.3}px -${rodHeight * 0.15}px rgba(255,255,255,0.2)`,
          }}
        >
          {/* Объемный эффект - радиальный градиент для цилиндра */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background: `radial-gradient(ellipse at center 20%, rgba(255,255,255,0.15) 0%, transparent 50%)`,
              zIndex: 1,
            }}
          />
          
          {/* Glossy effect (если включен) */}
          {isGlossy && (
            <>
              {/* Основной блик сверху */}
              <div
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: `${rodHeight * 0.3}px`,
                  background: 'linear-gradient(to bottom, rgba(255,255,255,0.5) 0%, rgba(255,255,255,0.3) 50%, transparent 100%)',
                  filter: 'blur(2px)',
                  zIndex: 3,
                }}
              />
              {/* Дополнительный боковой блик для объёма */}
              <div
                style={{
                  position: 'absolute',
                  top: `${rodHeight * 0.1}px`,
                  left: `${rodWidth * 0.05}px`,
                  width: `${rodWidth * 0.3}px`,
                  height: `${rodHeight * 0.5}px`,
                  background: 'linear-gradient(to right, rgba(255,255,255,0.4) 0%, transparent 100%)',
                  borderRadius: `${borderRadius}px`,
                  filter: 'blur(3px)',
                  zIndex: 3,
                }}
              />
            </>
          )}
          
          {/* Filler overlay (если наполнитель не none) */}
          {filler !== 'none' && (
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                ...fillerStylesBody,
                zIndex: 2,
                opacity: opacity < 1 ? opacity : 1,
              }}
            />
          )}
        </div>

        {/* Rod End - круглая часть на конце, частично перекрывает Rod Body */}
        <div
          className="relative rounded-full overflow-hidden flex-shrink-0"
          style={{
            width: `${endSize}px`,
            height: `${endSize}px`,
            background: rodEndBg,
            border: `${borderWidth}px solid ${borderColor}`,
            marginLeft: size === 'medium' ? '-60px' : `-${endSize / 2}px`, // Для medium смещаем на -60px (влево), для других - перекрываем на половину диаметра
            zIndex: 1,
            // Кружок всегда непрозрачен, даже при активной прозрачности
            // Объемный эффект для торца цилиндра - внутренняя тень для объёмности
            // Для люминофора добавляем свечение границы
            boxShadow: isTransparent 
              ? filler === 'luminescent'
                ? `inset 0 0 15px rgba(0,0,0,0.2), 0 0 10px ${colors[0] || '#FFEB3B'}40, 0 0 20px ${colors[0] || '#FFEB3B'}30`
                : 'inset 0 0 15px rgba(0,0,0,0.2)'
              : filler === 'luminescent'
              ? `inset 0 0 ${endSize * 0.15}px rgba(0,0,0,0.3), inset 0 0 ${endSize * 0.3}px -${endSize * 0.15}px rgba(255,255,255,0.15), 0 0 10px ${colors[0] || '#FFEB3B'}40, 0 0 20px ${colors[0] || '#FFEB3B'}30`
              : `inset 0 0 ${endSize * 0.15}px rgba(0,0,0,0.3), inset 0 0 ${endSize * 0.3}px -${endSize * 0.15}px rgba(255,255,255,0.15)`,
          }}
        >
          {/* Объемный эффект - радиальный градиент для торца */}
          <div
            className="absolute inset-0 rounded-full pointer-events-none"
            style={{
              background: `radial-gradient(circle at 30% 30%, rgba(255,255,255,0.15) 0%, transparent 60%)`,
              zIndex: 1,
            }}
          />
          
          {/* Filler overlay (если наполнитель не none) */}
          {filler !== 'none' && (
            <div
              className="absolute inset-0 rounded-full pointer-events-none"
              style={{
                ...fillerStylesEnd,
                zIndex: 2,
                opacity: opacity < 1 ? opacity : 1,
              }}
            />
          )}
          
          {/* Иконка градусника для термохромного типа */}
          {colorType === 'thermochromic' && (
            <div
              className="absolute inset-0 flex items-center justify-center pointer-events-none"
              style={{
                zIndex: 3,
              }}
            >
              <Thermometer
                size={size === 'small' ? 14 : size === 'medium' ? 20 : 28}
                color={luminance > 0.5 ? '#1a1a1a' : '#FFFFFF'}
                strokeWidth={2.5}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
