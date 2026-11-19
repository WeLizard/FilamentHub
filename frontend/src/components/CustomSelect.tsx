/** Кастомный выпадающий список в стиле модалок */

import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { createPortal } from 'react-dom';
import { ChevronDown, Check } from 'lucide-react';
import { useModalPortalRef } from './ModalOverlay';

interface Option {
  value: string | number;
  label: string;
}

interface CustomSelectProps {
  value: string | number | null;
  onChange: (value: string | number | null) => void;
  options: Option[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

interface DropdownPosition {
  top?: number;
  bottom?: number;
  left: number;
  width: number;
  maxHeight: number;
}

const DROPDOWN_GAP = 8; // mt-2
const DROPDOWN_MAX_HEIGHT = 240; // max-h-60
const DROPDOWN_OPTION_HEIGHT = 49; // py-3 + text line + divider
const VIEWPORT_MARGIN = 8;

/**
 * Opens the list below the button, or above it when the space below is too
 * small for the list and the space above is larger; the list never leaves the
 * viewport.
 */
export const computeDropdownPosition = (
  rect: Pick<DOMRect, 'top' | 'bottom' | 'left' | 'width'>,
  viewportHeight: number,
  optionCount: number,
): DropdownPosition => {
  const wanted = Math.min(DROPDOWN_MAX_HEIGHT, Math.max(1, optionCount) * DROPDOWN_OPTION_HEIGHT);
  const spaceBelow = Math.max(0, viewportHeight - rect.bottom - DROPDOWN_GAP - VIEWPORT_MARGIN);
  const spaceAbove = Math.max(0, rect.top - DROPDOWN_GAP - VIEWPORT_MARGIN);
  const base = { left: rect.left, width: rect.width };
  if (spaceBelow < wanted && spaceAbove > spaceBelow) {
    return {
      ...base,
      bottom: viewportHeight - rect.top + DROPDOWN_GAP,
      maxHeight: Math.min(DROPDOWN_MAX_HEIGHT, spaceAbove),
    };
  }
  return {
    ...base,
    top: rect.bottom + DROPDOWN_GAP,
    maxHeight: Math.min(DROPDOWN_MAX_HEIGHT, spaceBelow),
  };
};

export const CustomSelect: React.FC<CustomSelectProps> = ({
  value,
  onChange,
  options,
  placeholder: placeholderProp,
  className = '',
  disabled = false,
}) => {
  const { t } = useTranslation();
  const placeholder = placeholderProp ?? t('common.select');
  const [isOpen, setIsOpen] = useState(false);
  const [position, setPosition] = useState<DropdownPosition | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const modalPortalRef = useModalPortalRef(dropdownRef);

  // Вычисляем позицию выпадающего списка и обновляем при скролле/ресайзе
  useEffect(() => {
    if (!isOpen || !buttonRef.current) return;

    const updatePosition = () => {
      if (buttonRef.current) {
        setPosition(computeDropdownPosition(
          buttonRef.current.getBoundingClientRect(),
          window.innerHeight,
          options.length,
        ));
      }
    };

    updatePosition();

    // Обновляем позицию при скролле и ресайзе
    window.addEventListener('scroll', updatePosition, true);
    window.addEventListener('resize', updatePosition);

    return () => {
      window.removeEventListener('scroll', updatePosition, true);
      window.removeEventListener('resize', updatePosition);
    };
  }, [isOpen, options.length]);

  // Закрытие при клике вне компонента и скролле
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node) &&
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const selectedOption = options.find((opt) => opt.value === value);

  return (
    <>
      <div className={`relative ${className}`}>
        <button
          ref={buttonRef}
          type="button"
          onClick={() => { if (!disabled) setIsOpen(!isOpen); }}
          disabled={disabled}
          className={`w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all flex items-center justify-between ${disabled ? 'opacity-60 cursor-not-allowed' : ''}`}
        >
          <span className={selectedOption ? 'text-white' : 'text-gray-400'}>
            {selectedOption ? selectedOption.label : placeholder}
          </span>
          <ChevronDown
            className={`w-5 h-5 text-gray-400 transition-transform ${isOpen ? 'transform rotate-180' : ''}`}
          />
        </button>
      </div>

      {isOpen &&
        position &&
        createPortal(
          <div
            ref={modalPortalRef}
            data-modal-portal=""
            className="absolute z-[9999] bg-white/5 backdrop-blur-sm rounded-xl border border-white/10 shadow-xl overflow-hidden"
            style={{
              top: position.top === undefined ? undefined : `${position.top}px`,
              bottom: position.bottom === undefined ? undefined : `${position.bottom}px`,
              left: `${position.left}px`,
              width: `${position.width}px`,
              position: 'fixed',
            }}
          >
            <div className="overflow-y-auto custom-scrollbar" style={{ maxHeight: `${position.maxHeight}px` }}>
              {options.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => {
                    onChange(option.value);
                    setIsOpen(false);
                  }}
                  className={`w-full px-4 py-3 text-left hover:bg-white/10 transition-all border-b border-white/5 last:border-b-0 flex items-center justify-between ${
                    value === option.value ? 'bg-purple-600/20 text-purple-300' : 'text-white'
                  }`}
                >
                  <span>{option.label}</span>
                  {value === option.value && <Check className="w-5 h-5 text-purple-400" />}
                </button>
              ))}
            </div>
          </div>,
          document.body
        )}
    </>
  );
};

