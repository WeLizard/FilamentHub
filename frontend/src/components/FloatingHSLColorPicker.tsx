import { useLayoutEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { HSLColorPicker } from './HSLColorPicker';

interface FloatingHSLColorPickerProps {
  anchorElement: HTMLElement | null;
  color: string;
  isOpen: boolean;
  onChange: (hex: string) => void;
  onToggle: (isOpen: boolean) => void;
}

interface PickerPosition {
  left: number;
  top: number;
}

const PICKER_WIDTH = 240;
const PICKER_HEIGHT = 228;
const VIEWPORT_MARGIN = 12;
const ANCHOR_GAP = 8;

export const FloatingHSLColorPicker: React.FC<FloatingHSLColorPickerProps> = ({
  anchorElement,
  color,
  isOpen,
  onChange,
  onToggle,
}) => {
  const [position, setPosition] = useState<PickerPosition | null>(null);

  useLayoutEffect(() => {
    if (!isOpen || !anchorElement) {
      setPosition(null);
      return;
    }

    const updatePosition = () => {
      const rect = anchorElement.getBoundingClientRect();
      const halfWidth = PICKER_WIDTH / 2;
      const left = Math.min(
        Math.max(rect.left + rect.width / 2, VIEWPORT_MARGIN + halfWidth),
        window.innerWidth - VIEWPORT_MARGIN - halfWidth,
      );
      const top = Math.max(
        rect.top - ANCHOR_GAP,
        VIEWPORT_MARGIN + PICKER_HEIGHT,
      );

      setPosition({ left, top });
    };

    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);

    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [anchorElement, isOpen]);

  if (!isOpen || !position) return null;

  return createPortal(
    <div
      className="fixed z-[10000]"
      style={{
        left: position.left,
        top: position.top,
      }}
    >
      <HSLColorPicker
        color={color}
        onChange={onChange}
        isOpen
        onToggle={onToggle}
      />
    </div>,
    document.body,
  );
};
