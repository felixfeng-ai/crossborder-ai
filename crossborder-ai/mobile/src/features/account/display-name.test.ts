import { describe, expect, it } from "vitest";

import { formatGreetingName } from "./display-name";

describe("formatGreetingName", () => {
  it("保留八个及以内的中文称呼", () => {
    expect(formatGreetingName("小Veya商家")).toBe("小Veya商家");
  });

  it("超过八个字符时显示前六个字符并加省略号", () => {
    expect(formatGreetingName("一二三四五六七八九")).toBe("一二三四五六…");
  });

  it("去除称呼两端空白", () => {
    expect(formatGreetingName("  小Veya  ")).toBe("小Veya");
  });
});
