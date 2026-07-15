import type { ReactNode, SyntheticEvent } from 'react';

type BrandLogoFrameSize = 'cabinet' | 'hero' | 'preview' | 'thumbnail';

interface BrandLogoFrameProps {
  src?: string | null;
  alt: string;
  backgroundColor?: string | null;
  size?: BrandLogoFrameSize;
  fallback?: ReactNode;
  fallbackBackgroundClassName?: string;
  position?: 'relative' | 'absolute';
  className?: string;
  onError?: (event: SyntheticEvent<HTMLImageElement>) => void;
}

const frameSizeClasses: Record<BrandLogoFrameSize, string> = {
  cabinet:
    'min-h-14 min-w-14 max-w-16 p-1.5 md:min-h-16 md:min-w-16 md:max-w-[17rem] md:p-2.5',
  hero: 'min-h-24 min-w-24 max-w-full p-3',
  preview: 'min-h-16 min-w-16 max-w-56 p-2.5',
  thumbnail: 'min-h-10 min-w-10 max-w-28 p-1.5',
};

const imageSizeClasses: Record<BrandLogoFrameSize, string> = {
  cabinet: 'max-h-10 max-w-14 md:max-h-11 md:max-w-[15rem]',
  hero: 'max-h-16 max-w-56 sm:max-w-[20rem]',
  preview: 'max-h-11 max-w-48',
  thumbnail: 'max-h-7 max-w-24',
};

const positionClasses = {
  relative: 'relative',
  absolute: 'absolute',
} as const;

export function BrandLogoFrame({
  src,
  alt,
  backgroundColor,
  size = 'preview',
  fallback,
  fallbackBackgroundClassName = 'bg-white/10',
  position = 'relative',
  className = '',
  onError,
}: BrandLogoFrameProps) {
  const hasLogo = Boolean(src);

  return (
    <div
      className={`${positionClasses[position]} isolate inline-flex h-fit box-border shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-white/15 shadow-lg shadow-black/20 ring-1 ring-inset ring-white/10 ${frameSizeClasses[size]} ${
        hasLogo ? 'bg-white/10' : fallbackBackgroundClassName
      } ${className}`}
      style={hasLogo && backgroundColor ? { backgroundColor } : undefined}
      data-brand-logo-frame
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-0 bg-gradient-to-br from-white/15 via-transparent to-black/15"
      />
      {hasLogo ? (
        <img
          src={src!}
          alt={alt}
          className={`relative z-10 block h-auto w-auto object-contain drop-shadow-sm ${imageSizeClasses[size]}`}
          onError={onError}
        />
      ) : (
        <span className="relative z-10 flex items-center justify-center">{fallback}</span>
      )}
    </div>
  );
}
