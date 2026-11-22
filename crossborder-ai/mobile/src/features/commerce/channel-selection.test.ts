import { describe, expect, it } from "vitest";

import { parseChannelSelection } from "./channel-selection";

describe("店铺选择持久化", () => {
  it("恢复同一工作区内的店铺", () => {
    expect(
      parseChannelSelection(
        JSON.stringify({
          workspaceId: "workspace-1",
          channelType: "shopify",
          channelId: "store-1",
          name: "alpha",
        }),
        "workspace-1",
      ),
    ).toEqual({
      workspaceId: "workspace-1",
      channelType: "shopify",
      channelId: "store-1",
      name: "alpha",
    });
  });

  it("忽略损坏数据和跨工作区选择", () => {
    expect(parseChannelSelection("{bad", "workspace-1")).toBeNull();
    expect(
      parseChannelSelection(
        JSON.stringify({
          workspaceId: "workspace-2",
          channelType: "amazon",
          channelId: "store-1",
        }),
        "workspace-1",
      ),
    ).toBeNull();
  });
});
