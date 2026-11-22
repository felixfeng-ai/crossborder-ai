export function BrandMark({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 96 96"
      className={className}
      role="img"
      aria-label="VeyaShip"
      fill="none"
    >
      {/* 与 App AgentAvatar 共用黑圆、白色 V、底线和暖金星的几何比例。 */}
      <circle cx="48" cy="48" r="48" fill="#0B0E12" />
      <path
        d="M31 28 46 60 61 28"
        stroke="#FFFFFF"
        strokeWidth="8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M35 76h26"
        stroke="#FFFFFF"
        strokeWidth="7"
        strokeLinecap="round"
      />
      <path
        d="M72 11Q73 17.5 80 20Q73 22.5 72 29Q71 22.5 64 20Q71 17.5 72 11Z"
        fill="#E7A33A"
      />
    </svg>
  )
}
