import { describe, expect, it } from "vitest";

import {
  customerIntentLabel,
  customerRiskLabel,
} from "./risk-labels";

describe("客服风险标签", () => {
  it("把后端意图转换成卖家能快速理解的短标签", () => {
    expect(customerIntentLabel("refund_request")).toBe("退款请求");
    expect(customerIntentLabel("delivery_delay")).toBe("物流延迟");
    expect(customerIntentLabel("review_response")).toBe("评价回复");
    expect(customerIntentLabel("unknown")).toBe("客户消息");
  });

  it("高风险和待确认使用不同文案", () => {
    expect(customerRiskLabel("high")).toBe("高风险");
    expect(customerRiskLabel("medium")).toBe("需要确认");
    expect(customerRiskLabel("low")).toBe("常规");
  });
});
