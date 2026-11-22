import { describe, expect, it } from "vitest";

import {
  currentTimeZone,
  normalizeTimeZone,
} from "./timezone";

describe("工作区时区请求参数", () => {
  it("保留设备提供的 IANA 时区", () => {
    expect(normalizeTimeZone("America/Los_Angeles")).toBe(
      "America/Los_Angeles",
    );
  });

  it("空值或非法值回退到上海时区", () => {
    expect(normalizeTimeZone("")).toBe("Asia/Shanghai");
    expect(normalizeTimeZone("not/a-zone")).toBe("Asia/Shanghai");
  });

  it("设备无法解析时区时不抛错", () => {
    expect(currentTimeZone(() => "UTC")).toBe("UTC");
    expect(
      currentTimeZone(() => {
        throw new Error("unsupported");
      }),
    ).toBe("Asia/Shanghai");
  });
});
