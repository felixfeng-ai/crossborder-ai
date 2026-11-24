import { describe, expect, it } from "vitest";

import { buildSourceProfitPrompt } from "./prompt";

describe("mobile 1688 sourcing", () => {
  it("builds a profit prompt for a selected 1688 source", () => {
    const prompt = buildSourceProfitPrompt({
      item_id: "628196518518",
      title: "跨境无线宠物饮水机",
      url: "https://detail.1688.com/offer/628196518518.html",
      price: "18.50",
      moq: 2,
    });

    expect(prompt).toContain("analyze_product_decision");
    expect(prompt).toContain(
      "https://detail.1688.com/offer/628196518518.html",
    );
    expect(prompt).toContain("不要自动下单");
  });

});
