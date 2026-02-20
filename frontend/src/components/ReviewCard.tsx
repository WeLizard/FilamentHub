/** Компонент для отображения одного отзыва */

import React from 'react';
import { useTranslation } from 'react-i18next';
import { Star, CheckCircle, XCircle, Calendar, Edit, Trash2, Settings } from 'lucide-react';
import { Printer3DIcon } from './icons/Printer3DIcon';
import { FilamentReview } from '../types/api';
import { StarRating } from './StarRating';
import { BadgeList } from './Badge';

interface ReviewCardProps {
  review: FilamentReview;
  isOwn?: boolean; // Является ли отзыв текущего пользователя
  onEdit?: (review: FilamentReview) => void;
  onDelete?: (reviewId: number) => void;
}

export const ReviewCard: React.FC<ReviewCardProps> = ({
  review,
  isOwn = false,
  onEdit,
  onDelete,
}) => {
  const { t } = useTranslation();
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  return (
    <div className="bg-white/10 backdrop-blur-sm rounded-xl p-6 border border-white/20 hover:border-white/30 transition-colors">
      {/* Заголовок */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <div className="flex items-center space-x-3 mb-2">
            <h3 className="text-white font-semibold text-lg">
              {review.username || t('reviewCard.anonymousUser')}
            </h3>
            {review.user_badges && review.user_badges.length > 0 && (
              <BadgeList badges={review.user_badges as any} size="sm" />
            )}
            {isOwn && (
              <span className="px-2 py-1 bg-blue-500/20 text-blue-300 text-xs rounded-full border border-blue-500/30">
                {t('reviewCard.yourReview')}
              </span>
            )}
          </div>
          <div className="flex items-center space-x-4 text-sm text-gray-400">
            <div className="flex items-center space-x-1">
              <Calendar className="w-4 h-4" />
              <span>{formatDate(review.created_at)}</span>
            </div>
            {review.preset_name && (
              <div className="flex items-center space-x-1">
                <Settings className="w-4 h-4" />
                <span className="text-purple-300">{review.preset_name}</span>
              </div>
            )}
            {review.printer_model && (
              <div className="flex items-center space-x-1">
                <Printer3DIcon className="w-4 h-4" />
                <span>{review.printer_model}</span>
              </div>
            )}
          </div>
        </div>

        {/* Действия */}
        {isOwn && (onEdit || onDelete) && (
          <div className="flex items-center space-x-2">
            {onEdit && (
              <button
                onClick={() => onEdit(review)}
                className="p-2 text-gray-400 hover:text-blue-400 transition-colors rounded-lg hover:bg-white/10"
                title={t('reviewCard.editReview')}
              >
                <Edit className="w-4 h-4" />
              </button>
            )}
            {onDelete && (
              <button
                onClick={() => onDelete(review.id)}
                className="p-2 text-gray-400 hover:text-red-400 transition-colors rounded-lg hover:bg-white/10"
                title={t('reviewCard.deleteReview')}
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
          </div>
        )}
      </div>

      {/* Рейтинг и статус */}
      <div className="flex items-center space-x-4 mb-4">
        <StarRating rating={review.rating} readonly size="md" onChange={() => {}} />
        {review.success ? (
          <div className="flex items-center space-x-1 text-green-400">
            <CheckCircle className="w-5 h-5" />
            <span className="font-semibold">{t('reviewCard.successfulPrint')}</span>
          </div>
        ) : (
          <div className="flex items-center space-x-1 text-red-400">
            <XCircle className="w-5 h-5" />
            <span className="font-semibold">{t('reviewCard.printProblems')}</span>
          </div>
        )}
      </div>

      {/* Комментарий */}
      {review.comment && (
        <div className="mt-4">
          <p className="text-gray-300 whitespace-pre-wrap">{review.comment}</p>
        </div>
      )}
    </div>
  );
};



