import { useTranslation } from 'react-i18next';
import { AlertTriangle, X, CheckCircle, Shield } from 'lucide-react';
import { ReactNode } from 'react';
import { ModalOverlay } from './ModalOverlay';

interface ConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title?: string;
  message?: string;
  confirmText?: string;
  cancelText?: string;
  isLoading?: boolean;
  variant?: 'danger' | 'warning' | 'info' | 'success';
  icon?: ReactNode;
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title: titleProp,
  message,
  confirmText: confirmTextProp,
  cancelText: cancelTextProp,
  isLoading = false,
  variant = 'warning',
  icon,
}) => {
  const { t } = useTranslation();
  const title = titleProp ?? t('confirmModal.defaultTitle');
  const confirmText = confirmTextProp ?? t('confirmModal.confirm');
  const cancelText = cancelTextProp ?? t('confirmModal.cancel');

  if (!isOpen) return null;

  const variantStyles = {
    danger: {
      iconBg: 'bg-red-500/20',
      iconColor: 'text-red-400',
      buttonBg: 'bg-red-600 hover:bg-red-700',
      icon: <AlertTriangle className="w-5 h-5" />,
    },
    warning: {
      iconBg: 'bg-yellow-500/20',
      iconColor: 'text-yellow-400',
      buttonBg: 'bg-yellow-600 hover:bg-yellow-700',
      icon: <AlertTriangle className="w-5 h-5" />,
    },
    info: {
      iconBg: 'bg-blue-500/20',
      iconColor: 'text-blue-400',
      buttonBg: 'bg-blue-600 hover:bg-blue-700',
      icon: <Shield className="w-5 h-5" />,
    },
    success: {
      iconBg: 'bg-green-500/20',
      iconColor: 'text-green-400',
      buttonBg: 'bg-green-600 hover:bg-green-700',
      icon: <CheckCircle className="w-5 h-5" />,
    },
  };

  const style = variantStyles[variant];
  const displayIcon = icon || style.icon;

  return (
    <ModalOverlay onClose={onClose} closeOnOverlayClick={!isLoading}>
      <div
        className="bg-gradient-to-br from-purple-900 to-indigo-900 rounded-2xl max-w-md w-full overflow-hidden flex flex-col border border-white/20 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <div className="flex items-center space-x-3">
            <div className={`w-10 h-10 ${style.iconBg} rounded-lg flex items-center justify-center`}>
              <div className={style.iconColor}>
                {displayIcon}
              </div>
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
          <p className="text-gray-300 mb-6">{message}</p>

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
              className={`px-6 py-2.5 ${style.buttonBg} text-white rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2`}
            >
              {isLoading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>{t('confirmModal.executing')}</span>
                </>
              ) : (
                confirmText
              )}
            </button>
          </div>
        </div>
      </div>
    </ModalOverlay>
  );
};
