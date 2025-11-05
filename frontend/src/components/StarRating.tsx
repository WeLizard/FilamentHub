/** Компонент для выбора рейтинга звёздами */

import React from 'react';
import { Star } from 'lucide-react';

interface StarRatingProps {
  rating: number; // 0.0 - 5.0 (0 = не выбрано)
  onChange: (rating: number) => void;
  readonly?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export const StarRating: React.FC<StarRatingProps> = ({
  rating,
  onChange,
  readonly = false,
  size = 'md',
}) => {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-5 h-5',
    lg: 'w-6 h-6',
  };

  const handleClick = (value: number) => {
    if (!readonly) {
      onChange(value);
    }
  };

  const handleMouseEnter = (value: number) => {
    if (!readonly) {
      // Можно добавить hover эффект
    }
  };

  return (
    <div className="flex items-center space-x-1">
      {[1, 2, 3, 4, 5].map((value) => {
        const isFilled = rating >= value;
        const isHalf = rating >= value - 0.5 && rating < value;

        return (
          <button
            key={value}
            type="button"
            onClick={() => handleClick(value)}
            onMouseEnter={() => handleMouseEnter(value)}
            className={`${readonly ? 'cursor-default' : 'cursor-pointer hover:scale-110'} transition-transform ${sizeClasses[size]}`}
            disabled={readonly}
          >
            <Star
              className={`${sizeClasses[size]} ${
                isFilled
                  ? 'text-yellow-400 fill-current'
                  : isHalf
                  ? 'text-yellow-400 fill-current opacity-50'
                  : 'text-gray-400'
              }`}
            />
          </button>
        );
      })}
      {rating > 0 && !readonly && (
        <span className="ml-2 text-gray-300 text-sm">{rating.toFixed(1)}</span>
      )}
    </div>
  );
};



