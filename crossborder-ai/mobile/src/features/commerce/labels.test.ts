import { describe, expect, it } from "vitest";

import { commerceLabel, thumbnailsOf } from "./labels";

const base = {
  amount: null,
  currency: null,
  order_count: null,
  thumbnails: [],
};

describe("commerceLabel", () => {
  it("拼出「涉及 N 单 + 符号金额」", () => {
    expect(
      commerceLabel({
        ...base,
        amount: "1284.00",
        currency: "CNY",
        order_count: 2,
      }),
    ).toBe("涉及 2 单 ¥1,284");
  });

  it("没有订单数时只显示金额", () => {
    expect(commerceLabel({ ...base, amount: "86.5", currency: "USD" })).toBe(
      "$86.5",
    );
  });

  it("只有一单时不啰嗦「涉及 1 单」", () => {
    expect(
      commerceLabel({
        ...base,
        amount: "1284.00",
        currency: "CNY",
        order_count: 1,
      }),
    ).toBe("¥1,284");
  });

  it("认不出的币种显示代码，不冒充 ¥", () => {
    expect(commerceLabel({ ...base, amount: "320", currency: "nzd" })).toBe(
      "NZD 320",
    );
  });

  it("认识的币种用小写输入也能取到符号", () => {
    expect(commerceLabel({ ...base, amount: "320", currency: "aud" })).toBe(
      "A$320",
    );
  });

  it("缺币种时不加任何符号", () => {
    expect(commerceLabel({ ...base, amount: "1284" })).toBe("1,284");
  });

  it("金额不是数就原样输出，不吐 NaN", () => {
    expect(
      commerceLabel({ ...base, amount: "待核对", currency: "CNY" }),
    ).toBe("¥待核对");
  });

  it("没有金额或没有交易信息时返回 null，让界面整行不渲染", () => {
    expect(commerceLabel(null)).toBeNull();
    expect(commerceLabel(base)).toBeNull();
    expect(commerceLabel({ ...base, amount: "   " })).toBeNull();
  });
});

describe("thumbnailsOf", () => {
  it("最多三张并只留 http(s) 与同源绝对路径", () => {
    expect(
      thumbnailsOf([
        "https://cdn.shopify.com/a.jpg",
        "file:///etc/passwd",
        "  https://cdn.shopify.com/b.jpg  ",
        "https://cdn.shopify.com/c.jpg",
        "https://cdn.shopify.com/d.jpg",
      ]),
    ).toEqual([
      "https://cdn.shopify.com/a.jpg",
      "https://cdn.shopify.com/b.jpg",
      "https://cdn.shopify.com/c.jpg",
    ]);
  });

  it("保留以 / 开头的同源静态图，丢掉裸文件名", () => {
    expect(
      thumbnailsOf(["/preview/thumbs/earbuds.jpg", "earbuds.jpg", ""]),
    ).toEqual(["/preview/thumbs/earbuds.jpg"]);
  });

  it("空值安全", () => {
    expect(thumbnailsOf(null)).toEqual([]);
    expect(thumbnailsOf(undefined)).toEqual([]);
  });
});
