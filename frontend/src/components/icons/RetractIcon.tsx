// src/components/icons/RetractIcon.tsx
import * as React from 'react';

const RetractIcon = (props: React.SVGProps<SVGSVGElement>) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    {...props}
  >
    <circle cx={7} cy={12} r={3} />
    <line x1={7} y1={9} x2={7} y2={8} />
    <line x1={8.7} y1={10.3} x2={9.7} y2={9.3} />
    <line x1={10} y1={12} x2={11} y2={12} />
    <line x1={8.7} y1={13.7} x2={9.7} y2={14.7} />
    <line x1={7} y1={15} x2={7} y2={16} />
    <line x1={5.3} y1={13.7} x2={4.3} y2={14.7} />
    <line x1={4} y1={12} x2={3} y2={12} />
    <line x1={5.3} y1={10.3} x2={4.3} y2={9.3} />
    <circle cx={16} cy={12} r={2} />
    <line x1={12} y1={6} x2={12} y2={18} />
    <path d="M12 8v-2" />
    <path d="M10 6l2 -2l2 2" />
  </svg>
);

export default RetractIcon;