/** Универсальный компонент выпадающего списка для всего сайта */

import { useState, useRef, ReactNode, useEffect, useMemo, useId } from 'react';
import { useTranslation } from 'react-i18next';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, X } from 'lucide-react';

interface DropdownOption {
  value: string | number;
  label: string;
  icon?: ReactNode;
  /** Options sharing a group are listed together under its heading. */
  group?: string;
}

interface DropdownProps {
  value: string | number;
  options: DropdownOption[];
  onChange: (value: string | number) => void;
  placeholder?: string;
  label?: ReactNode;
  className?: string;
  disabled?: boolean;
  clearable?: boolean;
  filterable?: boolean; // Можно ли фильтровать по введенному тексту
  filterValue?: string; // Значение для фильтрации
  onFilterChange?: (value: string) => void; // Callback при изменении фильтра
  renderOption?: (option: DropdownOption) => ReactNode; // Кастомный рендеринг опции
  emptyMessage?: string; // Сообщение когда нет опций
  maxHeight?: string; // Максимальная высота списка
  size?: 'sm' | 'md'; // sm — компактный вариант для карточек/тулбаров
  multiple?: boolean; // Мультивыбор: опции переключаются, список не закрывается
  selectedValues?: (string | number)[]; // Выбранные значения в multiple-режиме
  onMultiChange?: (values: (string | number)[]) => void; // Callback multiple-режима
}

export const Dropdown: React.FC<DropdownProps> = ({
  value,
  options,
  onChange,
  placeholder: placeholderProp,
  label,
  className = '',
  disabled = false,
  clearable = true,
  filterable = false,
  filterValue = '',
  onFilterChange,
  renderOption,
  emptyMessage: emptyMessageProp,
  maxHeight = 'max-h-60',
  size = 'md',
  multiple = false,
  selectedValues = [],
  onMultiChange,
}) => {
  const { t } = useTranslation();
  const inputId = useId();
  const inputSizeClasses = size === 'sm' ? 'px-3 py-1.5 text-sm rounded-lg' : 'px-4 py-3 rounded-xl';
  const optionSizeClasses = size === 'sm' ? 'px-3 py-2 text-sm' : 'px-4 py-3';
  const selectedSet = new Set(selectedValues);
  const hasSelection = multiple ? selectedValues.length > 0 : value !== '';
  const placeholder = placeholderProp || t('dropdown.placeholder');
  const emptyMessage = emptyMessageProp || t('dropdown.emptyMessage');
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [filter, setFilter] = useState(filterValue || '');
  useEffect(() => {
    if (!filterable) {
      return;
    }
    if ((filterValue ?? '') !== filter) {
      setFilter(filterValue ?? '');
    }
  }, [filterValue, filterable]); 
  const [position, setPosition] = useState<{ top: number; left: number; width: number } | null>(null);

  // Вычисляем позицию выпадающего списка
  useEffect(() => {
    if (isOpen && inputRef.current) {
      const updatePosition = () => {
        if (inputRef.current) {
          const rect = inputRef.current.getBoundingClientRect();
          setPosition({
            top: rect.bottom + 4, // 4px отступ, fixed позиционирование относительно viewport
            left: rect.left,
            width: rect.width,
          });
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
    } else {
      setPosition(null);
    }
  }, [isOpen]);

  // Закрытие при клике вне компонента
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      const clickedInsideContainer = containerRef.current?.contains(target);
      const clickedInsideDropdown = dropdownRef.current?.contains(target);
      
      if (!clickedInsideContainer && !clickedInsideDropdown) {
        setIsOpen(false);
        if (filterable) {
          setFilter('');
          onFilterChange?.('');
        }
      }
    };

    // Используем capture phase для более раннего перехвата
    document.addEventListener('mousedown', handleClickOutside, true);
    document.addEventListener('click', handleClickOutside, true);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside, true);
      document.removeEventListener('click', handleClickOutside, true);
    };
  }, [isOpen, filterable, onFilterChange]);

  // Фильтруем опции если включена фильтрация
  const filteredOptions = useMemo(() => {
    if (!filterable || !filter) {
      return options;
    }
    const lowered = filter.toLowerCase();
    return options.filter((opt) => 
      opt.label.toLowerCase().includes(lowered) ||
      String(opt.value).toLowerCase().includes(lowered)
    );
  }, [filter, filterable, options]);

  const selectedOption = options.find(opt => opt.value === value);
  const multiLabel = multiple
    ? options.filter(opt => selectedSet.has(opt.value)).map(opt => opt.label).join(', ')
    : '';
  const displayLabel = multiple ? multiLabel : (selectedOption?.label || '');

  const handleClear = () => {
    if (multiple) {
      onMultiChange?.([]);
    } else if (clearable) {
      onChange('');
    }
    setIsOpen(false);
    if (filterable) {
      setFilter('');
      onFilterChange?.('');
    }
  };

  const handleInputChange = (newValue: string) => {
    if (filterable) {
      setFilter(newValue);
      onFilterChange?.(newValue);
      
      // Если поле фильтра полностью очищено (пользователь удалил весь текст через Backspace) - очищаем выбор
      if (clearable && newValue === '' && value !== '') {
        onChange('');
      }
    }
    if (!isOpen) {
      setIsOpen(true);
    }
  };

  const handleOptionClick = (optionValue: string | number) => {
    if (multiple) {
      // Toggle без закрытия — пользователь отмечает несколько опций подряд
      const next = selectedSet.has(optionValue)
        ? selectedValues.filter(v => v !== optionValue)
        : [...selectedValues, optionValue];
      onMultiChange?.(next);
      return;
    }
    onChange(optionValue);
    setIsOpen(false);
    if (filterable) {
      setFilter('');
      onFilterChange?.('');
    }
  };

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      {label && (
        <label htmlFor={inputId} className="block text-gray-300 mb-2 text-sm font-medium">
          {label}
        </label>
      )}
      
      <div className="relative">
        {filterable ? (
          <div className="relative">
            <input
              id={inputId}
              ref={inputRef}
              type="text"
              value={isOpen ? filter : displayLabel}
              onChange={(e) => handleInputChange(e.target.value)}
              onFocus={() => {
                setIsOpen(true);
                // Когда фильтром владеет родитель, подставлять сюда выбранное значение
                // нельзя: список сразу сузится до одного пункта, а родитель об этом не
                // узнает — его filterValue останется пустым.
                if (!onFilterChange && !filter && hasSelection && selectedOption) {
                  setFilter(selectedOption.label);
                }
              }}
              onKeyDown={(e) => {
                // Если нажали Escape и поле пустое - очищаем выбор
                if (clearable && e.key === 'Escape' && filter === '' && value !== '') {
                  handleClear();
                }
                if (e.key === 'Enter') {
                  e.preventDefault();
                  if (filteredOptions.length > 0) {
                    handleOptionClick(filteredOptions[0].value);
                  }
                }
              }}
              placeholder={placeholder}
              disabled={disabled}
              className={`w-full ${inputSizeClasses} ${hasSelection ? 'pr-10' : ''} bg-white/10 border border-white/20 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all ${
                disabled ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            />
            {clearable && hasSelection && !disabled && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleClear();
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-all"
                title={t('dropdown.clearSelection')}
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        ) : (
          <div className="relative">
            <input
              id={inputId}
              ref={inputRef}
              type="text"
              value={displayLabel}
              onFocus={() => setIsOpen(true)}
              placeholder={placeholder}
              disabled={disabled}
              readOnly
              className={`w-full ${inputSizeClasses} ${hasSelection ? 'pr-10' : ''} bg-white/10 border border-white/20 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all cursor-pointer ${
                disabled ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            />
            {!clearable && <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />}
            {clearable && hasSelection && !disabled && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleClear();
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-all"
                title={t('dropdown.clearSelection')}
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        )}

        {isOpen && position && createPortal(
          <div
            ref={dropdownRef}
            className="fixed z-[9999] overflow-hidden rounded-xl border border-white/20 bg-gray-800/90 shadow-xl backdrop-blur-md"
            style={{
              top: `${position.top}px`,
              left: `${position.left}px`,
              width: `${position.width}px`,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={`scrollbar-contained ${maxHeight} overflow-y-auto`}>
              {filteredOptions.length > 0 ? (
                filteredOptions.map((option, index) => (
                  <div key={option.value}>
                    {option.group && option.group !== filteredOptions[index - 1]?.group && (
                      <div className="px-3 pt-2 pb-1 text-[11px] uppercase tracking-wide text-gray-400">
                        {option.group}
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => handleOptionClick(option.value)}
                      className={`w-full ${optionSizeClasses} text-left hover:bg-white/10 transition-all text-white border-b border-white/5 last:border-b-0 flex items-center justify-between`}
                    >
                      {renderOption ? (
                        renderOption(option)
                      ) : (
                        <>
                          <span className="flex items-center gap-2">
                            {option.icon && <span>{option.icon}</span>}
                            <span>{option.label}</span>
                          </span>
                          {(multiple ? selectedSet.has(option.value) : value === option.value) && (
                            <Check className="w-5 h-5 text-purple-400 flex-shrink-0" />
                          )}
                        </>
                      )}
                    </button>
                  </div>
                ))
              ) : (
                <div className="px-4 py-3 text-gray-400 text-sm text-center">
                  {emptyMessage}
                </div>
              )}
            </div>
          </div>,
          document.body
        )}
      </div>
    </div>
  );
};

