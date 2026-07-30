/** Компонент секции цвета материала с поддержкой режимов preview и edit */

import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { createPortal } from 'react-dom';
import { FilamentPreview } from './FilamentPreview';
import { HSLColorPicker } from './HSLColorPicker';
import type { FilamentVisualSettings } from '../types/api';
import { formatRalCode, normalizeRalCode } from '../utils/ralCode';

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

  /** Необязательный четырёхзначный код RAL Classic */
  ralCode?: string;
  /** Callback при изменении RAL-кода */
  onRalCodeChange?: (value: string) => void;
  
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
  ralCode = '',
  onRalCodeChange,
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
      <label className="block text-gray-300 mb-2 text-sm font-medium">{t('colorMaterial.sectionLabel')}</label>
      
      {/* Flex layout: Название цвета | Preview | HEX - все выровнены по высоте */}
      <div className="grid grid-cols-1 items-end gap-3 sm:grid-cols-[minmax(12rem,1fr)_auto_8rem_7rem_auto]">
        {/* Инпут названия цвета (слева) */}
        <div className="min-w-0">
          <label className="block text-gray-400 mb-1 text-xs font-medium">{t('colorMaterial.colorName')}</label>
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
              {colorName || <span className="text-gray-400 italic">{t('colorMaterial.notSpecified')}</span>}
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
                    className="fixed z-[10000]"
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
          <label className="block text-gray-400 mb-1 text-xs font-medium">{t('colorMaterial.hexColor')}</label>
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

        {/* RAL — справочный код; экранный цвет по-прежнему задаётся HEX */}
        <div className="w-28">
          <label className="mb-1 block text-xs font-medium text-gray-400">{t('colorMaterial.ralCode')}</label>
          {isEditMode ? (
            <input
              type="text"
              value={ralCode}
              onChange={(event) => onRalCodeChange?.(event.target.value)}
              onBlur={(event) => onRalCodeChange?.(normalizeRalCode(event.target.value))}
              placeholder="RAL 3020"
              maxLength={8}
              className="h-12 w-full rounded-xl border border-white/20 bg-white/10 px-3 py-3 text-center font-mono text-sm text-white placeholder-gray-500 transition-all focus:border-transparent focus:outline-none focus:ring-2 focus:ring-purple-500"
              title={t('colorMaterial.ralHint')}
            />
          ) : (
            <div className="flex h-12 items-center rounded-xl border border-white/10 bg-white/5 px-3 font-mono text-sm text-white">
              {ralCode ? formatRalCode(ralCode) : <span className="text-gray-400">—</span>}
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
