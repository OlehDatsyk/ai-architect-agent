/** A wall outline with a door swing: the most basic symbol on any floor plan. */
export function BrandMark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={className}>
      <rect x="4" y="4" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="3" />
      <path d="M4 18 A10 10 0 0 1 14 28" fill="none" className="stroke-revision" strokeWidth="2" />
    </svg>
  );
}
