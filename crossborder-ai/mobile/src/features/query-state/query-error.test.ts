import { describe, expect, it } from "vitest";

import { describeQueryError } from "./query-error";

describe("query error copy", () => {
  it("reports a missing mobile API as a version mismatch", () => {
    expect(describeQueryError({ message: "Not Found", status: 404 })).toMatchObject({
      kind: "contract",
      title: "App 与服务器版本不一致",
    });
  });

  it("reports expired authentication separately from offline state", () => {
    expect(describeQueryError({ message: "Unauthorized", status: 401 })).toMatchObject({
      kind: "auth",
      title: "登录状态已失效",
    });
  });

  it("reports fetch failures as an offline or unreachable service", () => {
    expect(describeQueryError(new TypeError("Network request failed"))).toMatchObject({
      kind: "offline",
      title: "无法连接服务",
    });
  });

  it("reports server failures without blaming the user's network", () => {
    expect(describeQueryError({ message: "Internal Server Error", status: 500 })).toMatchObject({
      kind: "server",
      title: "服务暂时不可用",
    });
  });

  it("preserves a safe request error message for other HTTP failures", () => {
    expect(
      describeQueryError({ message: "请求过于频繁，请稍后再试", status: 429 }),
    ).toEqual({
      kind: "request",
      title: "请求暂时无法完成",
      description: "请求过于频繁，请稍后再试",
    });
    expect(describeQueryError({ status: 409 })).toMatchObject({
      kind: "request",
      description: "服务返回了异常状态，请稍后重试。",
    });
  });

  it("falls back for errors without enough diagnostic information", () => {
    expect(describeQueryError(new Error("Unexpected"))).toMatchObject({
      kind: "unknown",
      title: "暂时无法同步",
    });
    expect(describeQueryError({ status: "404" })).toMatchObject({
      kind: "unknown",
    });
    expect(describeQueryError(null)).toMatchObject({
      kind: "unknown",
    });
  });
});
