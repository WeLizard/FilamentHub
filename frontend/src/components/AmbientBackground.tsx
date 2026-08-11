export function AmbientBackground({ className = '' }: { className?: string }) {
  return (
    <div aria-hidden="true" className={`pointer-events-none fixed inset-0 overflow-hidden ${className}`}>
      <div className="absolute -right-40 -top-40 h-80 w-80 rounded-full bg-purple-500/10 blur-3xl" />
      <div className="absolute -bottom-40 -left-40 h-80 w-80 rounded-full bg-blue-500/10 blur-3xl" />
    </div>
  );
}
