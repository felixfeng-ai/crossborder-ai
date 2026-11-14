export function AssistantMark({
  className = '',
}: {
  className?: string
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      role="img"
      aria-label="AI 决策助手"
      fill="none"
    >
      <path
        d="M12 3.1V6.5"
        stroke="currentColor"
        strokeWidth="2.1"
        strokeLinecap="round"
      />
      <circle cx="12" cy="2.6" r="1.25" fill="currentColor" />
      <rect
        x="4.2"
        y="6.7"
        width="15.6"
        height="12"
        rx="4.2"
        stroke="currentColor"
        strokeWidth="2.1"
      />
      <path
        d="M4.2 11H2.4M21.6 11h-1.8"
        stroke="currentColor"
        strokeWidth="2.1"
        strokeLinecap="round"
      />
      <circle cx="9" cy="11.3" r="1.15" fill="currentColor" />
      <circle cx="15" cy="11.3" r="1.15" fill="currentColor" />
      <path
        d="M9.2 15.1h5.6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}
