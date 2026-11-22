import { describe, expect, it } from "vitest";

import {
  getPreviewTimeline,
  getPreviewWorkItem,
} from "./preview";

const listingId = "66666666-6666-4666-8666-666666666666";
const inventoryId = "77777777-7777-4777-8777-777777777777";
const refundId = "88888888-8888-4888-8888-888888888888";

describe("预览业务状态", () => {
  it("时间线包含上架、库存与退款入口", () => {
    const kinds = getPreviewTimeline().items.map((item) => item.kind);

    expect(kinds).toEqual(
      expect.arrayContaining([
        "listing_action",
        "inventory_action",
        "refund_action",
      ]),
    );
  });

  it.each([
    [listingId, "listings.publish", "即将发布商品"],
    [inventoryId, "inventory.update", "即将更新库存"],
    [refundId, "refunds.create", "即将发起退款"],
  ])("任务 %s 提供可审阅的确认预览", (id, actionId, title) => {
    const detail = getPreviewWorkItem(id);

    expect(detail.requires_action).toBe("confirm");
    expect(detail.action_runs[0]?.action_id).toBe(actionId);
    expect(detail.action_preview?.title).toBe(title);
    expect(detail.action_preview?.fields.length).toBeGreaterThan(1);
  });
});
