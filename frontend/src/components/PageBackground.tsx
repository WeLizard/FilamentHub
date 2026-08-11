import type { ReactNode } from 'react';
import { AmbientBackground } from './AmbientBackground';

interface PageBackgroundProps {
  children: ReactNode;
  className?: string;
  ambient?: boolean;
}

/** Shared full-page canvas for routes that are not already inside Layout. */
export function PageBackground({ children, className = '', ambient = false }: PageBackgroundProps) {
  return (
    <div className={`min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 ${className}`}>
      {ambient && <AmbientBackground />}
      {children}
    </div>
  );
}
