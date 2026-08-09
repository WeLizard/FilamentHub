interface FilamentSpoolIconProps {
  className?: string;
}

export function FilamentSpoolIcon({ className = '' }: FilamentSpoolIconProps) {
  return (
    <span
      aria-hidden="true"
      className={`block ${className}`}
      style={{
        backgroundColor: 'currentColor',
        WebkitMask: "url('/icons/filament-spool.svg') center / 112% 112% no-repeat",
        mask: "url('/icons/filament-spool.svg') center / 112% 112% no-repeat",
      }}
    />
  );
}
