export function BrandMark({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={className}
      role="img"
      aria-label="VeyaShip"
      fill="none"
    >
      <path
        d="M6.5 8.5 16 24.5 25.5 8.5"
        stroke="currentColor"
        strokeWidth="2.1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="6.5" cy="8.5" r="2" fill="currentColor" />
      <circle cx="16" cy="24.5" r="2.3" fill="var(--factory-accent)" />
      <circle cx="25.5" cy="8.5" r="2" fill="currentColor" />
      <path
        d="M22.5 18.5h4.5"
        stroke="var(--factory-accent)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeDasharray="2 2.5"
      />
      <circle cx="28" cy="18.5" r="1.4" fill="var(--factory-accent)" />
    </svg>
  )
}
