import { describe, expect, it } from "vitest";

import { moveVisibleAsset } from "./library-order";

const assets = [
  { id: "a" },
  { id: "b" },
  { id: "c" },
  { id: "d" },
];

describe("素材库筛选后排序", () => {
  it("只交换当前可见素材，隐藏素材相对顺序不变", () => {
    const next = moveVisibleAsset(
      assets,
      ["b", "d"],
      "d",
      -1,
    );

    expect(next.map((asset) => asset.id)).toEqual(["a", "d", "c", "b"]);
  });

  it("到达可见列表边界时保持不变", () => {
    const next = moveVisibleAsset(
      assets,
      ["b", "d"],
      "b",
      -1,
    );

    expect(next.map((asset) => asset.id)).toEqual(["a", "b", "c", "d"]);
  });
});
