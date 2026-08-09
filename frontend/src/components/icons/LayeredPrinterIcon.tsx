interface LayeredPrinterIconProps {
  className?: string;
}

export function LayeredPrinterIcon({ className = '' }: LayeredPrinterIconProps) {
  return (
    <span
      aria-hidden="true"
      className={`block ${className}`}
      style={{
        backgroundColor: 'currentColor',
        WebkitMask: "url('/icons/printer-layered.svg') center / contain no-repeat",
        mask: "url('/icons/printer-layered.svg') center / contain no-repeat",
      }}
    />
  );
}
