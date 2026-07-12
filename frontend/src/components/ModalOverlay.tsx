/** Shared modal overlay — portal, backdrop, centering, scroll lock, Escape */

import { ReactNode, useEffect, useCallback, useRef } from 'react';
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
  /** Classes for the inner content container (default centers the modal; override for drawers) */
  contentClassName?: string;
}

export const ModalOverlay: React.FC<ModalOverlayProps> = ({
  onClose,
  children,
  closeOnOverlayClick = true,
  closeOnEscape = true,
  className = '',
  contentClassName = 'min-h-full flex items-center justify-center p-4',
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

  // Track where the mouse press started. Closing only on a genuine
  // backdrop click (press AND release on the backdrop) prevents a text
  // selection that starts inside an input and ends over the backdrop from
  // wrongly closing the modal — Chromium fires a `click` on the common
  // ancestor (this backdrop) in that case, Firefox does not.
  const pressStartedOnOverlay = useRef(false);

  const handleOverlayMouseDown = (e: React.MouseEvent) => {
    pressStartedOnOverlay.current = e.target === e.currentTarget;
  };

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (closeOnOverlayClick && e.target === e.currentTarget && pressStartedOnOverlay.current) {
      onClose();
    }
    pressStartedOnOverlay.current = false;
  };

  return createPortal(
    <div className={`fixed inset-0 bg-black/50 backdrop-blur-sm z-[9999] overflow-y-auto ${className}`}>
      <div
        className={contentClassName}
        onMouseDown={handleOverlayMouseDown}
        onClick={handleOverlayClick}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
};
