import { createPortal } from 'react-dom';
import { AlertTriangle, X } from 'lucide-react';
import { useHeaderVisible } from '../hooks/useHeaderVisible';

interface ConfirmDeleteModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title?: string;
  message?: string;
  confirmText?: string;
  cancelText?: string;
  isLoading?: boolean;
  itemName?: string; // Опциональное имя элемента для удаления
}

export const ConfirmDeleteModal: React.FC<ConfirmDeleteModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title = 'Подтвердите удаление',
  message,
  confirmText = 'Удалить',
  cancelText = 'Отмена',
  isLoading = false,
  itemName,
}) => {
  if (!isOpen) return null;

  const defaultMessage = itemName
    ? `Вы уверены, что хотите удалить "${itemName}"? Это действие нельзя отменить.`
    : 'Вы уверены, что хотите удалить этот элемент? Это действие нельзя отменить.';

  const displayMessage = message || defaultMessage;
  const isHeaderVisible = useHeaderVisible();

  return createPortal(
    <div className={`fixed inset-0 bg-black/50 backdrop-blur-sm z-50 overflow-y-auto ${isHeaderVisible ? 'pt-[88px]' : ''}`}>
      <div className="min-h-full flex items-center justify-center p-4">
        <div className="bg-gradient-to-br from-purple-900 to-indigo-900 rounded-2xl max-w-md w-full overflow-hidden flex flex-col border border-white/20 shadow-xl">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-white/10">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-red-500/20 rounded-lg flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-red-400" />
              </div>
              <h3 className="text-xl font-bold text-white">{title}</h3>
            </div>
            <button
              onClick={onClose}
              disabled={isLoading}
              className="text-gray-400 hover:text-white transition-colors disabled:opacity-50"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <div className="p-6">
            <p className="text-gray-300 mb-6">{displayMessage}</p>

            {/* Actions */}
            <div className="flex items-center justify-end space-x-3">
              <button
                onClick={onClose}
                disabled={isLoading}
                className="px-6 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {cancelText}
              </button>
              <button
                onClick={onConfirm}
                disabled={isLoading}
                className="px-6 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
              >
                {isLoading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Удаление...</span>
                  </>
                ) : (
                  confirmText
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};

