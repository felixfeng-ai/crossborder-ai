import { describe, expect, it } from "vitest";

import {
  buildAgentFollowUpText,
  parseAgentMarkdown,
  parseInlineMarkdown,
  turnNeedsUserInput,
} from "./result-presentation";

describe("Agent result presentation", () => {
  it("把标题、编号列表和段落解析成紧凑结构", () => {
    const blocks = parseAgentMarkdown(
      "## 需要补充\n1. **商品链接**：请发 1688 链接\n2. 目标平台：Amazon\n\n你把链接发我后继续。",
    );

    expect(blocks).toEqual([
      { type: "heading", text: "需要补充" },
      { type: "ordered", index: "1", text: "**商品链接**：请发 1688 链接" },
      { type: "ordered", index: "2", text: "目标平台：Amazon" },
      { type: "paragraph", text: "你把链接发我后继续。" },
    ]);
  });

  it("把行内加粗拆成可渲染片段，不显示 Markdown 星号", () => {
    expect(parseInlineMarkdown("请补充 **1688 链接** 后继续")).toEqual([
      { text: "请补充 ", bold: false },
      { text: "1688 链接", bold: true },
      { text: " 后继续", bold: false },
    ]);
  });

  it("等待补充时保持会话可继续", () => {
    expect(
      turnNeedsUserInput("waiting_user", [
        { status: "needs_input" },
      ]),
    ).toBe(true);
    expect(turnNeedsUserInput("succeeded", [])).toBe(false);
  });

  it("补充信息会携带上一轮上下文继续同一任务", () => {
    const text = buildAgentFollowUpText({
      previousInput: "帮我上架一个新品",
      previousResult: "请补充 1688 商品链接。",
      reply: "https://detail.1688.com/offer/123.html",
    });

    expect(text).toContain("延续上一轮任务");
    expect(text).toContain("帮我上架一个新品");
    expect(text).toContain("请补充 1688 商品链接");
    expect(text).toContain("https://detail.1688.com/offer/123.html");
  });
});
