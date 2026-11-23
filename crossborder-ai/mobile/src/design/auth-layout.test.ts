import { describe, expect, it } from "vitest";

// 登录页视觉规格必须保持可追踪，避免后续样式改动绕过设计契约。
import {
  nextPasswordVisibility,
  SIGN_IN_COLORS,
  SIGN_IN_INTERACTION,
  SIGN_IN_LAYOUT,
  SIGN_IN_TYPE,
  validateUsername,
  WORDMARK_RENDER_MODE,
} from "./auth-layout";

describe("sign-in design contract", () => {
  it("uses the requested 390pt frame and 26pt margins", () => {
    expect(SIGN_IN_LAYOUT.designWidth).toBe(390);
    expect(SIGN_IN_LAYOUT.horizontalInset).toBe(26);
    expect(SIGN_IN_LAYOUT.contentWidth).toBe(338);
  });

  it("keeps the requested control sizes and vertical rhythm", () => {
    expect(SIGN_IN_LAYOUT.logoTop).toBe(150);
    expect(SIGN_IN_LAYOUT.logoSize).toBe(62);
    expect(SIGN_IN_LAYOUT.logoToWordmark).toBe(26);
    expect(SIGN_IN_LAYOUT.wordmarkToTagline).toBe(20);
    expect(SIGN_IN_LAYOUT.taglineToFields).toBe(36);
    expect(SIGN_IN_LAYOUT.fieldHeight).toBe(54);
    expect(SIGN_IN_LAYOUT.fieldGap).toBe(8);
    expect(SIGN_IN_LAYOUT.fieldsToButton).toBe(28);
    expect(SIGN_IN_LAYOUT.buttonHeight).toBe(52);
    expect(SIGN_IN_LAYOUT.buttonToLegal).toBe(22);
    expect(SIGN_IN_LAYOUT.legalToCreateAccount).toBe(28);
    expect(SIGN_IN_LAYOUT.keyboardScrollY).toBe(104);
    expect(SIGN_IN_LAYOUT.buttonHeight).toBeGreaterThanOrEqual(44);
  });

  it("uses the exact palette and type scale", () => {
    expect(SIGN_IN_COLORS).toMatchObject({
      background: "#F7F8F9",
      ink: "#111213",
      secondary: "#66717C",
      placeholder: "#68707C",
      border: "#DDE2E6",
      focusedBorder: "#111213",
      cursor: "#111213",
      button: "#111315",
    });
    expect(SIGN_IN_TYPE).toMatchObject({
      wordmark: 44,
      tagline: 14,
      input: 15,
      button: 17,
      legal: 12,
      createAccount: 14,
    });
  });

  it("keeps one reversed black primary button with no gradient", () => {
    expect(SIGN_IN_COLORS.button).toBe("#111315");
    expect(SIGN_IN_INTERACTION.pressedOpacity).toBe(0.92);
    // 按钮高必须接近输入框高：超过 1.2 倍整页就失衡。
    expect(SIGN_IN_LAYOUT.buttonHeight).toBeLessThanOrEqual(
      SIGN_IN_LAYOUT.fieldHeight * 1.2,
    );
  });

  it("does not add a focus border and keeps the password state explicit", () => {
    expect(SIGN_IN_INTERACTION.showFocusRing).toBe(false);
    expect(SIGN_IN_INTERACTION.usernameDebounceMs).toBe(400);
    expect(nextPasswordVisibility(false)).toBe(true);
    expect(nextPasswordVisibility(true)).toBe(false);
  });

  it("validates usernames with the requested 4-12 character rule", () => {
    expect(validateUsername("小Veya")).toBeNull();
    expect(validateUsername("小V")).toBe("format");
    expect(validateUsername("小Veya 测试")).toBe("format");
    expect(validateUsername("小Veya-测试")).toBe("format");
    expect(validateUsername("一二三四五六七八九十一二三")).toBe("format");
  });

  it("requires a non-font SVG wordmark", () => {
    expect(WORDMARK_RENDER_MODE).toBe("svg");
  });
});
