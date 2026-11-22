import { describe, expect, it } from "vitest";

import type { NotificationItem, TimelineItem } from "@/api/types";

import { buildFunctionHub } from "./catalog";

function item(
  overrides: Partial<TimelineItem> & Pick<TimelineItem, "id" | "kind">,
): TimelineItem {
  return {
    title: "任务",
    summary: "任务摘要",
    status: "waiting_user",
    priority: "normal",
    current_step: "等待你决定",
    requires_action: "confirm",
    version: 1,
    due_at: null,
    occurred_at: "2026-11-19T01:00:00.000Z",
    ...overrides,
  };
}

function notification(
  overrides: Partial<NotificationItem> &
    Pick<NotificationItem, "id">,
): NotificationItem {
  return {
    notification_type: "needs_action",
    title: "通知",
    body: "通知正文",
    deep_link: "/",
    work_item_id: null,
    status: "sent",
    created_at: "2026-11-19T01:00:00.000Z",
    read_at: null,
    ...overrides,
  };
}

describe("buildFunctionHub", () => {
  it("直接打开优先级更高的待处理业务工作项", () => {
    const model = buildFunctionHub({
      items: [
        item({
          id: "order-normal",
          kind: "order_exception",
          priority: "attention",
        }),
        item({
          id: "order-urgent",
          kind: "order_exception",
          priority: "urgent",
        }),
        item({
          id: "message-1",
          kind: "customer_reply",
          priority: "attention",
        }),
      ],
      notifications: [],
      decisionCount: 0,
    });

    const order = model.sections
      .flatMap((section) => section.shortcuts)
      .find((shortcut) => shortcut.id === "orders");
    const pending = model.sections
      .flatMap((section) => section.shortcuts)
      .find((shortcut) => shortcut.id === "pending-messages");

    expect(order).toMatchObject({
      count: 2,
      target: { type: "work-item", workItemId: "order-urgent" },
    });
    expect(pending).toMatchObject({
      count: 1,
      target: { type: "work-item", workItemId: "message-1" },
    });
    expect(model.common.some((shortcut) => shortcut.id === "messages")).toBe(
      false,
    );
  });

  it("没有待处理工作项时返回首页预填 Agent 指令", () => {
    const model = buildFunctionHub({
      items: [],
      notifications: [],
      decisionCount: 0,
    });

    const inventory = model.sections
      .flatMap((section) => section.shortcuts)
      .find((shortcut) => shortcut.id === "inventory");

    expect(inventory).toMatchObject({
      count: 0,
      target: {
        type: "draft",
        text: "帮我检查库存和价格是否需要调整",
      },
    });
  });

  it("已完成的业务工作项不计入数量且不作为直达目标", () => {
    const model = buildFunctionHub({
      items: [
        item({
          id: "message-done",
          kind: "customer_reply",
          status: "succeeded",
          requires_action: "none",
          priority: "normal",
        }),
      ],
      notifications: [],
      decisionCount: 0,
    });

    const customer = model.sections.find((section) => section.id === "customer");

    expect(customer?.shortcuts.map((shortcut) => shortcut.id)).toEqual([
      "pending-messages",
      "review-replies",
      "complaints",
    ]);
    expect(
      customer?.shortcuts.every(
        (shortcut) =>
          shortcut.count === 0 && shortcut.target.type === "draft",
      ),
    ).toBe(true);
  });

  it("客户工作项只进入一个唯一分类", () => {
    const model = buildFunctionHub({
      items: [
        item({
          id: "complaint",
          kind: "customer_reply",
          title: "差评投诉升级",
          summary: "买家要求平台介入。",
        }),
        item({
          id: "review",
          kind: "customer_reply",
          title: "差评评价回复",
          summary: "需要回复评价。",
        }),
        item({
          id: "message",
          kind: "customer_reply",
          title: "物流咨询",
          summary: "买家询问包裹进度。",
        }),
      ],
      notifications: [],
      decisionCount: 0,
    });
    const customer = model.sections.find(
      (section) => section.id === "customer",
    );
    const counts = Object.fromEntries(
      customer?.shortcuts.map((shortcut) => [
        shortcut.id,
        shortcut.count,
      ]) ?? [],
    );

    expect(counts).toEqual({
      "pending-messages": 1,
      "review-replies": 1,
      complaints: 1,
    });
  });

  it("使用真实的计划数和未读通知数打开现有系统页面", () => {
    const model = buildFunctionHub({
      items: [],
      notifications: [
        notification({ id: "n1" }),
        notification({
          id: "n2",
          read_at: "2026-11-19T02:00:00.000Z",
        }),
        notification({ id: "n3" }),
      ],
      decisionCount: 3,
    });

    const system = model.sections.find((section) => section.id === "system");
    const plan = system?.shortcuts.find((shortcut) => shortcut.id === "plan");
    const activity = system?.shortcuts.find(
      (shortcut) => shortcut.id === "activity",
    );
    const account = system?.shortcuts.find(
      (shortcut) => shortcut.id === "account",
    );

    expect(plan).toMatchObject({
      count: 3,
      target: { type: "route", href: "/plan" },
    });
    expect(activity).toMatchObject({
      count: 2,
      target: { type: "route", href: "/activity" },
    });
    expect(account).toMatchObject({
      count: 0,
      target: { type: "route", href: "/account" },
    });
  });

  it("只把素材类 agent_action 归入素材入口", () => {
    const model = buildFunctionHub({
      items: [
        item({
          id: "media-1",
          kind: "agent_action",
          title: "三张商品场景图已生成",
          status: "waiting_user",
        }),
        item({
          id: "other-agent",
          kind: "agent_action",
          title: "发布商品到 Shopify",
        }),
      ],
      notifications: [],
      decisionCount: 0,
    });

    const media = model.sections
      .flatMap((section) => section.shortcuts)
      .find((shortcut) => shortcut.id === "media");

    expect(media).toMatchObject({
      count: 1,
      target: { type: "work-item", workItemId: "media-1" },
    });

    const assetLibrary = model.sections
      .flatMap((section) => section.shortcuts)
      .find((shortcut) => shortcut.id === "asset-library");
    expect(assetLibrary).toMatchObject({
      target: { type: "route", href: "/library" },
    });
  });
});
