import { beforeEach, describe, expect, it, vi } from "vitest";

const secure = vi.hoisted(() => ({
  deleteSecureItem: vi.fn(),
  getSecureItem: vi.fn(),
  setSecureItem: vi.fn(),
}));

vi.mock("@/security/storage", () => secure);
vi.mock("@/features/commerce/channel-selection", () => ({
  parseChannelSelection: vi.fn(() => null),
}));

// Mock 必须先注册，确保工作区 store 使用测试存储。
// eslint-disable-next-line import/first
import { useWorkspaceStore } from "./workspace";

describe("workspace session boundary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.setState({
      activeWorkspaceId: "workspace-old",
      activeChannel: {
        workspaceId: "workspace-old",
        channelType: "shopify",
        channelId: "store-old",
        name: "Old store",
      },
    });
    secure.deleteSecureItem.mockResolvedValue(undefined);
  });

  it("clears in-memory workspace before secure deletion finishes", async () => {
    const finishDeletions: (() => void)[] = [];
    secure.deleteSecureItem.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          finishDeletions.push(resolve);
        }),
    );

    const pending = useWorkspaceStore.getState().clear();
    await vi.waitFor(() => {
      expect(useWorkspaceStore.getState().activeWorkspaceId).toBeNull();
    });
    expect(useWorkspaceStore.getState().activeChannel).toBeNull();

    finishDeletions.forEach((finish) => finish());
    await pending;
  });
});
