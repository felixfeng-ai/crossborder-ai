export function AssistantMark({
  className = '',
}: {
  className?: string
}) {
  return (
    <svg
      viewBox="0 0 128 128"
      className={className}
      role="img"
      aria-label="AI 决策助手"
      fill="none"
    >
      <path
        d="M38 20H90L110 40V91L91 110H37L18 91V40L38 20Z"
        fill="#151815"
        stroke="#D8B56D"
        strokeWidth="4"
      />
      <path
        d="M86 22 106 12 103 34"
        stroke="#D8B56D"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="106" cy="12" r="4" fill="#9FC8B7" />
      <path
        d="M39 49 64 91 89 49"
        stroke="#F3F0E8"
        strokeWidth="6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="39" cy="49" r="5" fill="#F3F0E8" />
      <circle cx="89" cy="49" r="5" fill="#9FC8B7" />
      <circle cx="64" cy="91" r="6" fill="#D8B56D" />
      <path
        d="M31 72H45"
        stroke="#9FC8B7"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <path
        d="M83 72H97"
        stroke="#D8B56D"
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray="4 5"
      />
      <circle cx="101" cy="72" r="3" fill="#D8B56D" />
    </svg>
  )
}
