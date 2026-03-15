/** Shared modal overlay — portal, backdrop, centering, scroll lock, Escape */

import { ReactNode, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';

let scrollLockCount = 0;

interface ModalOverlayProps {
  onClose: () => void;
  children: ReactNode;
  /** Close when clicking outside the modal content (default: true) */
  closeOnOverlayClick?: boolean;
  /** Close on Escape key (default: true) */
  closeOnEscape?: boolean;
  /** Extra classes for the outer fixed overlay div */
  className?: string;
}

export const ModalOverlay: React.FC<ModalOverlayProps> = ({
  onClose,
  children,
  closeOnOverlayClick = true,
  closeOnEscape = true,
  className = '',
}) => {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (!closeOnEscape) return;
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [closeOnEscape, handleKeyDown]);

  useEffect(() => {
    scrollLockCount++;
    if (scrollLockCount === 1) {
      document.body.style.overflow = 'hidden';
    }
    return () => {
      scrollLockCount--;
      if (scrollLockCount === 0) {
        document.body.style.overflow = '';
      }
    };
  }, []);

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (closeOnOverlayClick && e.target === e.currentTarget) {
      onClose();
    }
  };

  return createPortal(
    <div className={`fixed inset-0 bg-black/50 backdrop-blur-sm z-[9999] overflow-y-auto ${className}`}>
      <div
        className="min-h-full flex items-center justify-center p-4"
        onClick={handleOverlayClick}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
};
