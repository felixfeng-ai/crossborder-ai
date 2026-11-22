import { describe, expect, it } from "vitest";

import { parseAppDeepLink } from "./deep-link-parse";

const workspaceId = "99999999-9999-4999-8999-999999999999";
const taskId = "11111111-1111-4111-8111-111111111111";

describe("App 深链解析", () => {
  it("解析任务深链并保留工作区", () => {
    expect(
      parseAppDeepLink(`/t/${taskId}?workspaceId=${workspaceId}`),
    ).toEqual({
      kind: "task",
      workItemId: taskId,
      workspaceId,
    });
  });

  it("计划与通知深链保留工作区", () => {
    expect(
      parseAppDeepLink(`/plan?workspaceId=${workspaceId}`),
    ).toEqual({ kind: "plan", workspaceId });
    expect(
      parseAppDeepLink(`/activity?workspaceId=${workspaceId}`),
    ).toEqual({ kind: "activity", workspaceId });
  });

  it("拒绝无效工作区和未知路径", () => {
    expect(
      parseAppDeepLink(`/t/${taskId}?workspaceId=../../etc`),
    ).toEqual({ kind: "task", workItemId: taskId });
    expect(parseAppDeepLink("/unknown")).toBeNull();
  });
});
