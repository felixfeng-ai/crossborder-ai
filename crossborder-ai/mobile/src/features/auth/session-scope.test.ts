import { describe, expect, it, vi } from "vitest";

import { clearUserRuntimeState } from "./session-scope";

describe("user runtime state reset", () => {
  it("clears old-account queries, workspace and composer before a new login", async () => {
    const calls: string[] = [];
    const dependencies = {
      cancelQueries: vi.fn(async () => {
        calls.push("cancelQueries");
      }),
      clearQueries: vi.fn(() => {
        calls.push("clearQueries");
      }),
      clearWorkspace: vi.fn(async () => {
        calls.push("clearWorkspace");
      }),
      resetComposer: vi.fn(() => {
        calls.push("resetComposer");
      }),
    };

    await clearUserRuntimeState(dependencies);

    expect(calls).toEqual([
      "cancelQueries",
      "clearQueries",
      "resetComposer",
      "clearWorkspace",
    ]);
  });

  it("keeps query data cleared even when local workspace deletion fails", async () => {
    const dependencies = {
      cancelQueries: vi.fn().mockResolvedValue(undefined),
      clearQueries: vi.fn(),
      clearWorkspace: vi.fn().mockRejectedValue(new Error("storage offline")),
      resetComposer: vi.fn(),
    };

    await expect(clearUserRuntimeState(dependencies)).rejects.toThrow(
      "storage offline",
    );
    expect(dependencies.clearQueries).toHaveBeenCalledOnce();
    expect(dependencies.resetComposer).toHaveBeenCalledOnce();
  });
});
