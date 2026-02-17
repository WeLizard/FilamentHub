/** Универсальный компонент выпадающего списка для всего сайта */

import { useState, useRef, ReactNode, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { createPortal } from 'react-dom';
import { Check, X } from 'lucide-react';

interface DropdownOption {
  value: string | number;
  label: string;
  icon?: ReactNode;
}

interface DropdownProps {
  value: string | number;
  options: DropdownOption[];
  onChange: (value: string | number) => void;
  placeholder?: string;
  label?: string;
  className?: string;
  disabled?: boolean;
  filterable?: boolean; // Можно ли фильтровать по введенному тексту
  filterValue?: string; // Значение для фильтрации
  onFilterChange?: (value: string) => void; // Callback при изменении фильтра
  renderOption?: (option: DropdownOption) => ReactNode; // Кастомный рендеринг опции
  emptyMessage?: string; // Сообщение когда нет опций
  maxHeight?: string; // Максимальная высота списка
}

export const Dropdown: React.FC<DropdownProps> = ({
  value,
  options,
  onChange,
  placeholder: placeholderProp,
  label,
  className = '',
  disabled = false,
  filterable = false,
  filterValue = '',
  onFilterChange,
  renderOption,
  emptyMessage: emptyMessageProp,
  maxHeight = 'max-h-60',
}) => {
  const { t } = useTranslation();
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

  const handleClear = () => {
    onChange('');
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
      if (newValue === '' && value !== '') {
        onChange('');
      }
    }
    if (!isOpen) {
      setIsOpen(true);
    }
  };

  const handleOptionClick = (optionValue: string | number) => {
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
        <label className="block text-gray-300 mb-2 text-sm font-medium">
          {label}
        </label>
      )}
      
      <div className="relative">
        {filterable ? (
          <div className="relative">
            <input
              ref={inputRef}
              type="text"
              value={isOpen ? filter : (selectedOption?.label || '')}
              onChange={(e) => handleInputChange(e.target.value)}
              onFocus={() => {
                setIsOpen(true);
                if (!filter && selectedOption) {
                  setFilter(selectedOption.label);
                }
              }}
              onKeyDown={(e) => {
                // Если нажали Escape и поле пустое - очищаем выбор
                if (e.key === 'Escape' && filter === '' && value !== '') {
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
              className={`w-full px-4 py-3 ${value !== '' ? 'pr-10' : ''} bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all ${
                disabled ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            />
            {value !== '' && !disabled && (
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
              ref={inputRef}
              type="text"
              value={selectedOption?.label || ''}
              onFocus={() => setIsOpen(true)}
              placeholder={placeholder}
              disabled={disabled}
              readOnly
              className={`w-full px-4 py-3 ${value !== '' ? 'pr-10' : ''} bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all cursor-pointer ${
                disabled ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            />
            {value !== '' && !disabled && (
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
            className={`fixed z-[9999] ${maxHeight} overflow-y-auto bg-gray-800/90 backdrop-blur-md rounded-xl border border-white/20 shadow-xl`}
            style={{
              top: `${position.top}px`,
              left: `${position.left}px`,
              width: `${position.width}px`,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {filteredOptions.length > 0 ? (
              filteredOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => handleOptionClick(option.value)}
                  className="w-full px-4 py-3 text-left hover:bg-white/10 transition-all text-white border-b border-white/5 last:border-b-0 flex items-center justify-between"
                >
                  {renderOption ? (
                    renderOption(option)
                  ) : (
                    <>
                      <span className="flex items-center gap-2">
                        {option.icon && <span>{option.icon}</span>}
                        <span>{option.label}</span>
                      </span>
                      {value === option.value && (
                        <Check className="w-5 h-5 text-purple-400 flex-shrink-0" />
                      )}
                    </>
                  )}
                </button>
              ))
            ) : (
              <div className="px-4 py-3 text-gray-400 text-sm text-center">
                {emptyMessage}
              </div>
            )}
          </div>,
          document.body
        )}
      </div>
    </div>
  );
};

