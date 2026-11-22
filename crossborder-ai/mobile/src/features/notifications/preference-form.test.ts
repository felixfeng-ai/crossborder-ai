import { describe, expect, it } from "vitest";

import {
  canEditNotificationPreferences,
  formatHour,
  validatePreferenceDraft,
} from "./preference-form";

describe("通知偏好表单", () => {
  it("只有 owner/admin/operator 可以修改", () => {
    expect(canEditNotificationPreferences("owner")).toBe(true);
    expect(canEditNotificationPreferences("admin")).toBe(true);
    expect(canEditNotificationPreferences("operator")).toBe(true);
    expect(canEditNotificationPreferences("viewer")).toBe(false);
  });

  it("小时使用两位显示，空值表示不启用免打扰", () => {
    expect(formatHour(8)).toBe("08:00");
    expect(formatHour(null)).toBe("不启用");
  });

  it("非法时区会被拒绝，起止小时必须合法", () => {
    expect(
      validatePreferenceDraft({
        timezone: "Asia/Shanghai",
        quietStartHour: 22,
        quietEndHour: 8,
      }),
    ).toBe("");
    expect(
      validatePreferenceDraft({
        timezone: "not/a-zone",
        quietStartHour: 22,
        quietEndHour: 8,
      }),
    ).toBe("请输入有效的 IANA 时区");
    expect(
      validatePreferenceDraft({
        timezone: "Asia/Shanghai",
        quietStartHour: 24,
        quietEndHour: 8,
      }),
    ).toBe("免打扰小时必须在 0–23 之间");
  });
});
