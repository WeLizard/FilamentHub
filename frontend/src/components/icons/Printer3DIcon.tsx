import React from 'react';

interface Printer3DIconProps {
  className?: string;
  size?: number;
  strokeWidth?: number;
}

export const Printer3DIcon: React.FC<Printer3DIconProps> = ({
  className = '',
  size = 24,
  strokeWidth = 2
}) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width={size}
    height={size}
    viewBox="0 0 22 22"
    className={className}
  >
    {/* Корпус */}
    <rect x={1} y={1} width={20} height={20} rx={2.33} ry={2.33} fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    {/* Куб на столе */}
    <rect x={9} y={13} width={4} height={3} fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    {/* Верхняя панель */}
    <rect x={1} y={4} width={20} height={3} fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    {/* Сопло */}
    <polygon points="9.13 7 11 10 13 7 9.13 7" fill="currentColor" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    {/* Стол */}
    <line x1={6} y1={18.34} x2={16} y2={18.34} stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export default Printer3DIcon;
