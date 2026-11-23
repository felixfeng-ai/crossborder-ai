export const SIGN_IN_COLORS = {
  background: "#F7F8F9",
  ink: "#111213",
  secondary: "#66717C",
  placeholder: "#68707C",
  border: "#DDE2E6",
  focusedBorder: "#111213",
  white: "#FFFFFF",
  logo: "#0B0C0E",
  createAccountMuted: "#66717C",
  // 主按钮反相纯黑卡：与工作台黑卡同一种材质，不再使用渐变。
  button: "#111315",
} as const;

export const SIGN_IN_TYPE = {
  wordmark: 44,
  tagline: 14,
  input: 15,
  button: 17,
  legal: 12,
  createAccount: 14,
} as const;

export const SIGN_IN_LAYOUT = {
  designWidth: 390,
  designHeight: 844,
  horizontalInset: 26,
  contentWidth: 338,
  logoTop: 150,
  logoSize: 62,
  logoToWordmark: 26,
  wordmarkToTagline: 20,
  taglineToFields: 36,
  fieldHeight: 54,
  fieldGap: 8,
  fieldRadius: 14,
  fieldsToButton: 28,
  // 与输入框接近等高：按钮高 ≈ 输入框高 × 0.96，超过 1.2 倍即失衡。
  buttonHeight: 52,
  controlRadius: 14,
  buttonToLegal: 22,
  legalToCreateAccount: 28,
  fieldHorizontalPadding: 18,
  fieldIconSize: 18,
} as const;

/**
 * 登录页只允许按下时的不透明度反馈，不允许渐变、光晕或描边光环。
 */
export const SIGN_IN_INTERACTION = {
  showFocusRing: false,
  pressedOpacity: 0.92,
  usernameDebounceMs: 400,
} as const;

export const WORDMARK_RENDER_MODE = "svg" as const;

const USERNAME_PATTERN = /^[\u4e00-\u9fffA-Za-z0-9_]{4,12}$/u;

export function nextPasswordVisibility(visible: boolean) {
  return !visible;
}

export function validateUsername(value: string) {
  return USERNAME_PATTERN.test(value) ? null : "format";
}
