import type { NotificationItem, TimelineItem } from "@/api/types";

export type FunctionShortcutTarget =
  | { type: "work-item"; workItemId: string }
  | {
      type: "route";
      href: "/library" | "/plan" | "/activity" | "/account" | "/stores";
    }
  | { type: "draft"; text: string };

export type FunctionShortcut = {
  id: string;
  title: string;
  detail: string;
  count: number;
  target: FunctionShortcutTarget;
};

export type FunctionSection = {
  id: string;
  title: string;
  shortcuts: FunctionShortcut[];
};

export type FunctionHubModel = {
  common: FunctionShortcut[];
  sections: FunctionSection[];
};

type BuildFunctionHubInput = {
  items: TimelineItem[];
  notifications: NotificationItem[];
  decisionCount: number;
};

const priorityRank: Record<string, number> = {
  urgent: 0,
  attention: 1,
  normal: 2,
};

function openItems(items: TimelineItem[]) {
  return items
    .filter(
      (item) =>
        item.requires_action !== "none" &&
        item.status !== "succeeded" &&
        item.status !== "cancelled",
    )
    .sort(
      (left, right) =>
        (priorityRank[left.priority] ?? 3) -
        (priorityRank[right.priority] ?? 3),
    );
}

function customerReplyCategory(item: TimelineItem) {
  const copy = `${item.title} ${item.summary}`;
  if (/投诉|不满|纠纷|维权|平台介入/i.test(copy)) {
    return "complaint";
  }
  if (/评价|评论|差评|review/i.test(copy)) {
    return "review";
  }
  return "pending";
}

function businessShortcut(
  id: string,
  title: string,
  detail: string,
  matches: (item: TimelineItem) => boolean,
  draftText: string,
  items: TimelineItem[],
): FunctionShortcut {
  const matched = openItems(items).filter(matches);
  return {
    id,
    title,
    detail,
    count: matched.length,
    target: matched[0]
      ? { type: "work-item", workItemId: matched[0].id }
      : { type: "draft", text: draftText },
  };
}

export function buildFunctionHub(
  input: BuildFunctionHubInput,
): FunctionHubModel {
  const orders = businessShortcut(
    "orders",
    "订单异常",
    "超时、履约与物流问题",
    (item) => item.kind === "order_exception",
    "帮我检查今天的订单异常和履约情况",
    input.items,
  );
  // 「客户与评价」组：同一批 customer_reply 按买家意图拆成三行，计数互补、不重复。
  // 常用区不再重复放「客户消息」，避免与这一组撞车。
  const pendingMessages = businessShortcut(
    "pending-messages",
    "待回复消息",
    "买家咨询还没回复",
    (item) =>
      item.kind === "customer_reply" &&
      customerReplyCategory(item) === "pending",
    "帮我检查还没回复的买家消息",
    input.items,
  );
  const reviewReplies = businessShortcut(
    "review-replies",
    "评价回复",
    "买家评价与差评回应",
    (item) =>
      item.kind === "customer_reply" &&
      customerReplyCategory(item) === "review",
    "帮我处理还没回复的买家评价",
    input.items,
  );
  const complaints = businessShortcut(
    "complaints",
    "投诉与风险",
    "需要升级处理的问题",
    (item) =>
      item.kind === "customer_reply" &&
      customerReplyCategory(item) === "complaint",
    "帮我看看有没有需要升级处理的买家投诉",
    input.items,
  );
  const inventory = businessShortcut(
    "inventory",
    "库存与价格",
    "低库存、缺货与价格调整",
    (item) => item.kind === "inventory_action",
    "帮我检查库存和价格是否需要调整",
    input.items,
  );
  const refund = businessShortcut(
    "refund",
    "退款与售后",
    "待处理退款和售后方案",
    (item) => item.kind === "refund_action",
    "帮我检查需要处理的退款和售后",
    input.items,
  );
  const listing = businessShortcut(
    "listing",
    "商品上架",
    "选品、Listing 与发布",
    (item) => item.kind === "listing_action",
    "帮我上架一个新商品",
    input.items,
  );
  const media = businessShortcut(
    "media",
    "素材生成",
    "商品图片与视频结果",
    (item) =>
      item.kind === "agent_action" &&
      /图片|场景图|主图|视频|素材/.test(`${item.title} ${item.summary}`),
    "帮我为商品生成一组图片素材",
    input.items,
  );

  const plan: FunctionShortcut = {
    id: "plan",
    title: "今日计划",
    detail: "需要你决定的工作",
    count: input.decisionCount,
    target: { type: "route", href: "/plan" },
  };
  const activity: FunctionShortcut = {
    id: "activity",
    title: "通知",
    detail: "异常、结果与系统提醒",
    count: input.notifications.filter((item) => !item.read_at).length,
    target: { type: "route", href: "/activity" },
  };
  const account: FunctionShortcut = {
    id: "account",
    title: "账号与工作区",
    detail: "工作区、角色与退出设备",
    count: 0,
    target: { type: "route", href: "/account" },
  };
  const stores: FunctionShortcut = {
    id: "stores",
    title: "店铺与渠道",
    detail: "连接、查看和检查店铺授权",
    count: 0,
    target: { type: "route", href: "/stores" },
  };
  const assetLibrary: FunctionShortcut = {
    id: "asset-library",
    title: "素材库",
    detail: "排序、替换与移除图片",
    count: 0,
    target: { type: "route", href: "/library" },
  };

  return {
    common: [orders, listing, plan],
    sections: [
      {
        id: "product",
        title: "商品与上架",
        shortcuts: [listing, inventory, media, assetLibrary],
      },
      {
        id: "customer",
        title: "客户与评价",
        shortcuts: [pendingMessages, reviewReplies, complaints],
      },
      {
        id: "order",
        title: "订单与履约",
        shortcuts: [orders, refund],
      },
      {
        id: "system",
        title: "计划与设置",
        shortcuts: [stores, plan, activity, account],
      },
    ],
  };
}
