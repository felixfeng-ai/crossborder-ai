import { describe, expect, it } from "vitest";

import { shouldShowSendButton } from "./composer-state";

describe("composer send button", () => {
  it("非空文字输入时显示发送按钮", () => {
    expect(shouldShowSendButton({ value: "帮我上架一个新产品", voiceMode: false }))
      .toBe(true);
  });

  it("空输入或语音模式不显示文字发送按钮", () => {
    expect(shouldShowSendButton({ value: "   ", voiceMode: false })).toBe(false);
    expect(shouldShowSendButton({ value: "测试", voiceMode: true })).toBe(false);
  });
});
