import { describe, expect, it } from "vitest";

import { workspaceRoleLabel, workspaceTypeLabel } from "./account-labels";

describe("account labels", () => {
  it("把工作区角色转换为卖家可读的中文", () => {
    expect(workspaceRoleLabel("owner")).toBe("所有者");
    expect(workspaceRoleLabel("admin")).toBe("管理员");
    expect(workspaceRoleLabel("operator")).toBe("运营");
    expect(workspaceRoleLabel("viewer")).toBe("只读成员");
  });

  it("把工作区类型转换为中文并保留未知值", () => {
    expect(workspaceTypeLabel("personal")).toBe("个人");
    expect(workspaceTypeLabel("team")).toBe("团队");
    expect(workspaceTypeLabel("custom")).toBe("custom");
  });

  it("为空和未知角色提供稳定兜底", () => {
    expect(workspaceRoleLabel(null)).toBe("未知角色");
    expect(workspaceRoleLabel("custom")).toBe("custom");
    expect(workspaceTypeLabel(undefined)).toBe("未知类型");
  });
});
