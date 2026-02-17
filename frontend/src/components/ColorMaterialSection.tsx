/** Компонент секции цвета материала с поддержкой режимов preview и edit */

import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { createPortal } from 'react-dom';
import { FilamentPreview } from './FilamentPreview';
import { HSLColorPicker } from './HSLColorPicker';
import type { FilamentVisualSettings } from '../types/api';

interface ColorMaterialSectionProps {
  /** Режим работы: preview (только отображение) или edit (редактирование) */
  mode?: 'preview' | 'edit';
  
  /** Название цвета */
  colorName: string;
  /** Callback при изменении названия цвета (только в режиме edit) */
  onColorNameChange?: (value: string) => void;
  
  /** HEX цвет */
  colorHex: string;
  /** Callback при изменении HEX цвета (только в режиме edit) */
  onColorHexChange?: (value: string) => void;
  
  /** Расширенные визуальные настройки (опционально) */
  visualSettings?: FilamentVisualSettings | null;
  
  /** Размер превью филамента */
  previewSize?: 'small' | 'medium' | 'large';
  
  /** Класс для контейнера */
  className?: string;
  
  /** Опциональная кнопка справа от HEX инпута */
  rightButton?: React.ReactNode;
}

export const ColorMaterialSection: React.FC<ColorMaterialSectionProps> = ({
  mode = 'edit',
  colorName,
  onColorNameChange,
  colorHex,
  onColorHexChange,
  visualSettings,
  previewSize = 'medium',
  className = '',
  rightButton,
}) => {
  const { t } = useTranslation();
  const isEditMode = mode === 'edit';
  const [isColorPickerOpen, setIsColorPickerOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const [pickerPosition, setPickerPosition] = useState<{ bottom: number; left: number } | null>(null);

  // Высота соответствует высоте input полей (py-3 = 12px padding сверху/снизу, плюс высота текста)
  // Input поля имеют высоту примерно 48px (h-12)
  const fieldHeight = '48px'; // h-12 в Tailwind

  // Вычисляем позицию пикера для portal
  useEffect(() => {
    if (isColorPickerOpen && buttonRef.current) {
      const updatePosition = () => {
        if (buttonRef.current) {
          const rect = buttonRef.current.getBoundingClientRect();
          // Пикер должен быть над кнопкой, используем bottom позиционирование
          // bottom = расстояние от нижнего края viewport до верхнего края кнопки
          const viewportHeight = window.innerHeight;
          const bottom = viewportHeight - rect.top;
          setPickerPosition({
            bottom: bottom + 10, // 10px отступ над кнопкой
            left: rect.left + rect.width / 2, // Центр кнопки
          });
        }
      };

      updatePosition();
      window.addEventListener('scroll', updatePosition, true);
      window.addEventListener('resize', updatePosition);

      return () => {
        window.removeEventListener('scroll', updatePosition, true);
        window.removeEventListener('resize', updatePosition);
      };
    } else {
      setPickerPosition(null);
    }
  }, [isColorPickerOpen]);

  return (
    <div className={className}>
      <label className="block text-gray-300 mb-2 text-sm font-medium">Цвет материала</label>
      
      {/* Flex layout: Название цвета | Preview | HEX - все выровнены по высоте */}
      <div className="flex items-end gap-4 justify-between">
        {/* Инпут названия цвета (слева) */}
        <div className="flex-[0_1_auto] min-w-[250px]">
          <label className="block text-gray-400 mb-1 text-xs font-medium">Название цвета</label>
          {isEditMode ? (
            <input
              type="text"
              value={colorName}
              onChange={(e) => onColorNameChange?.(e.target.value)}
              placeholder={t('createFilament.colorNamePlaceholder')}
              className="w-full h-12 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 placeholder:text-center focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
            />
          ) : (
            <div className="h-12 px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white flex items-center">
              {colorName || <span className="text-gray-400 italic">Не указано</span>}
            </div>
          )}
        </div>

        {/* Визуальное превью прутка - кликабельная кнопка для выбора цвета */}
        {/* Масштабируем FilamentPreview до 48px (medium = 60px, scale = 48/60 = 0.8) */}
        <div 
          className="flex-shrink-0 relative flex items-center justify-center"
          style={{ height: fieldHeight }}
        >
          {isEditMode ? (
            <div className="relative flex items-center justify-center h-full">
              {/* Filament Preview - кликабельная кнопка для открытия пикера */}
              <div className="relative z-10">
                <button
                  ref={buttonRef}
                  type="button"
                  onClick={() => setIsColorPickerOpen(!isColorPickerOpen)}
                  className="cursor-pointer hover:opacity-80 transition-opacity flex items-center justify-center h-full"
                  title={t('createFilament.clickToPickColor')}
                >
                  <div style={{ transform: 'scale(0.8)', transformOrigin: 'center' }}>
                    <FilamentPreview
                      colorHex={colorHex}
                      visualSettings={visualSettings}
                      size={previewSize}
                    />
                  </div>
                </button>
                {/* HSL Color Picker - рендерим через portal вне модального окна */}
                {isColorPickerOpen && pickerPosition && createPortal(
                  <div
                    className="fixed z-[200]"
                    style={{
                      bottom: `${pickerPosition.bottom}px`,
                      left: `${pickerPosition.left}px`,
                      transform: 'translateX(-50%)',
                    }}
                  >
                  <HSLColorPicker
                    color={colorHex}
                    onChange={(hex) => onColorHexChange?.(hex)}
                    isOpen={isColorPickerOpen}
                    onToggle={setIsColorPickerOpen}
                  />
                  </div>,
                  document.body
                )}
              </div>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center">
              <div style={{ transform: 'scale(0.8)', transformOrigin: 'center' }}>
                <FilamentPreview
                  colorHex={colorHex}
                  visualSettings={visualSettings}
                  size={previewSize}
                />
              </div>
            </div>
          )}
        </div>

        {/* Инпут HEX (справа) */}
        <div className="w-32">
          <label className="block text-gray-400 mb-1 text-xs font-medium">Цвет HEX</label>
          {isEditMode ? (
            <input
              type="text"
              value={colorHex}
              onChange={(e) => {
                // Разрешаем свободный ввод - можно писать любой текст
                onColorHexChange?.(e.target.value);
              }}
              placeholder="#FF0000"
              className="w-full h-12 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 placeholder:text-center focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all font-mono text-sm"
            />
          ) : (
            <div className="h-12 px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white flex items-center font-mono text-sm">
              {colorHex || <span className="text-gray-400 italic">#000000</span>}
            </div>
          )}
        </div>

        {/* Опциональная кнопка справа от HEX инпута */}
        {rightButton && (
          <div className="flex items-end flex-shrink-0">
            {rightButton}
          </div>
        )}
      </div>
    </div>
  );
};
