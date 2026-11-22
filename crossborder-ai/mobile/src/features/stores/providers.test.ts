import { describe, expect, it } from "vitest";

import {
  STORE_PROVIDERS,
  normalizeShopInput,
  storeStatusLabel,
} from "./providers";

describe("store connection providers", () => {
  it("提供 Shopify、Amazon 和 Temu 三个真实入口", () => {
    expect(STORE_PROVIDERS.map((provider) => provider.id)).toEqual([
      "shopify",
      "amazon",
      "temu",
    ]);
  });

  it("Shopify 接受裸子域和完整域名", () => {
    expect(normalizeShopInput("demo-store")).toBe("demo-store");
    expect(normalizeShopInput("https://demo-store.myshopify.com/")).toBe(
      "demo-store",
    );
    expect(normalizeShopInput("bad shop")).toBeNull();
  });

  it("店铺状态使用可读中文", () => {
    expect(storeStatusLabel("active")).toBe("已连接");
    expect(storeStatusLabel("inactive")).toBe("已停用");
  });
});
