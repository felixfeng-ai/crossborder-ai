import { create } from "zustand";

import type { WorkspaceSummary } from "@/api/types";
import {
  deleteSecureItem,
  getSecureItem,
  setSecureItem,
} from "@/security/storage";
import {
  parseChannelSelection,
  type ChannelSelection,
} from "@/features/commerce/channel-selection";

const WORKSPACE_KEY = "veyaship.mobile.workspace_id";
const CHANNEL_KEY = "veyaship.mobile.commerce_channel";

type WorkspaceState = {
  activeWorkspaceId: string | null;
  activeChannel: ChannelSelection | null;
  hydrate: () => Promise<void>;
  setActiveWorkspace: (workspace: WorkspaceSummary) => Promise<void>;
  setActiveWorkspaceId: (workspaceId: string) => Promise<void>;
  setActiveChannel: (channel: ChannelSelection | null) => Promise<void>;
  clear: () => Promise<void>;
};

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  activeWorkspaceId: null,
  activeChannel: null,
  hydrate: async () => {
    const [id, rawChannel] = await Promise.all([
      getSecureItem(WORKSPACE_KEY),
      getSecureItem(CHANNEL_KEY),
    ]);
    set({
      activeWorkspaceId: id,
      activeChannel: parseChannelSelection(rawChannel, id),
    });
  },
  setActiveWorkspace: async (workspace) => {
    const changed =
      useWorkspaceStore.getState().activeWorkspaceId !== workspace.id;
    await Promise.all([
      setSecureItem(WORKSPACE_KEY, workspace.id),
      changed ? deleteSecureItem(CHANNEL_KEY) : Promise.resolve(),
    ]);
    set({
      activeWorkspaceId: workspace.id,
      ...(changed ? { activeChannel: null } : {}),
    });
  },
  setActiveWorkspaceId: async (workspaceId) => {
    const changed =
      useWorkspaceStore.getState().activeWorkspaceId !== workspaceId;
    set({
      activeWorkspaceId: workspaceId,
      ...(changed ? { activeChannel: null } : {}),
    });
    await Promise.all([
      setSecureItem(WORKSPACE_KEY, workspaceId),
      changed ? deleteSecureItem(CHANNEL_KEY) : Promise.resolve(),
    ]);
  },
  setActiveChannel: async (channel) => {
    set({ activeChannel: channel });
    if (channel) {
      await setSecureItem(CHANNEL_KEY, JSON.stringify(channel));
    } else {
      await deleteSecureItem(CHANNEL_KEY);
    }
  },
  clear: async () => {
    await Promise.all([
      deleteSecureItem(WORKSPACE_KEY),
      deleteSecureItem(CHANNEL_KEY),
    ]);
    set({ activeWorkspaceId: null, activeChannel: null });
  },
}));
