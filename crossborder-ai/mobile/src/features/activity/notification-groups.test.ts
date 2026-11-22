import { describe, expect, it } from "vitest";

import type { NotificationItem } from "@/api/types";

import { groupNotificationsByDay } from "./notification-groups";

function notification(
  id: string,
  createdAt: string,
  overrides: Partial<NotificationItem> = {},
): NotificationItem {
  return {
    id,
    notification_type: "needs_action",
    title: "需要你决定",
    body: "通知正文",
    deep_link: "/",
    work_item_id: null,
    status: "sent",
    created_at: createdAt,
    read_at: null,
    ...overrides,
  };
}

describe("groupNotificationsByDay", () => {
  it("按工作区时区分组今天、昨天和更早日期", () => {
    const groups = groupNotificationsByDay(
      [
        notification("today-late", "2026-11-19T09:42:00.000Z"),
        notification("today-early", "2026-11-19T01:18:00.000Z"),
        notification("yesterday", "2026-11-18T12:00:00.000Z"),
        notification("older", "2026-11-17T12:00:00.000Z"),
      ],
      {
        now: new Date("2026-11-19T04:00:00.000Z"),
        timeZone: "Asia/Shanghai",
      },
    );

    expect(groups.map((group) => group.title)).toEqual([
      "今天",
      "昨天",
      "11月17日",
    ]);
    expect(groups[0].items.map((item) => item.id)).toEqual([
      "today-late",
      "today-early",
    ]);
  });

  it("补充时间、业务标签和未读状态", () => {
    const [group] = groupNotificationsByDay(
      [
        notification("needs-action", "2026-11-19T09:42:00.000Z"),
        notification("brief", "2026-11-19T08:00:00.000Z", {
          notification_type: "morning_brief",
          read_at: "2026-11-19T08:30:00.000Z",
        }),
        notification("failed", "2026-11-19T07:00:00.000Z", {
          notification_type: "action_failed",
        }),
      ],
      {
        now: new Date("2026-11-19T10:00:00.000Z"),
        timeZone: "Asia/Shanghai",
      },
    );

    expect(group.items[0]).toMatchObject({
      id: "needs-action",
      timeLabel: "17:42",
      typeLabel: "待处理",
      unread: true,
    });
    expect(group.items[1]).toMatchObject({
      id: "brief",
      typeLabel: "今日计划",
      unread: false,
    });
    expect(group.items[2]).toMatchObject({
      id: "failed",
      typeLabel: "执行失败",
    });
  });

  it("使用运行环境时区并给未知通知类型提供兜底标签", () => {
    const [group] = groupNotificationsByDay(
      [
        notification("unknown", "2026-11-19T09:42:00.000Z", {
          notification_type: "custom_type",
        }),
      ],
      { now: new Date("2026-11-19T09:42:00.000Z") },
    );

    expect(group.title).toBe("今天");
    expect(group.items[0].typeLabel).toBe("提醒");
  });
});
