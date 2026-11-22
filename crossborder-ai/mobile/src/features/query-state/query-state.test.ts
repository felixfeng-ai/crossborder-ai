import { describe, expect, it } from "vitest";

import { resolveQueryState } from "./query-state";

describe("查询界面状态", () => {
  it("首次加载优先显示加载态", () => {
    expect(
      resolveQueryState({ isLoading: true, isError: false, hasData: false }),
    ).toBe("loading");
  });

  it("请求失败且没有缓存时显示错误态", () => {
    expect(
      resolveQueryState({ isLoading: false, isError: true, hasData: false }),
    ).toBe("error");
  });

  it("有旧数据时刷新失败仍保留内容", () => {
    expect(
      resolveQueryState({ isLoading: false, isError: true, hasData: true }),
    ).toBe("content");
  });

  it("正常无数据显示空态", () => {
    expect(
      resolveQueryState({ isLoading: false, isError: false, hasData: false }),
    ).toBe("empty");
  });
});
