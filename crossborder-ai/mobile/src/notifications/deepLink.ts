import { router } from "expo-router";

import { deleteSecureItem, getSecureItem, setSecureItem } from "@/security/storage";
import { useWorkspaceStore } from "@/stores/workspace";
import { parseAppDeepLink } from "./deep-link-parse";

export const PENDING_DEEP_LINK_KEY = "veyaship_pending_deep_link";

export function navigateDeepLink(deepLink: string) {
  const target = parseAppDeepLink(deepLink);
  if (!target) return false;
  if (target.workspaceId) {
    // 先同步 store，确保目标页面首次查询就使用通知所属工作区。
    void useWorkspaceStore
      .getState()
      .setActiveWorkspaceId(target.workspaceId);
  }
  if (target.kind === "task") {
    router.push({
      pathname: "/task/[workItemId]",
      params: {
        workItemId: target.workItemId,
        workspaceId: target.workspaceId ?? "",
      },
    });
    return true;
  }
  if (target.kind === "plan") {
    router.push("/plan");
    return true;
  }
  if (target.kind === "activity") {
    router.push("/activity");
    return true;
  }
  return false;
}

export async function savePendingDeepLink(deepLink: string) {
  await setSecureItem(PENDING_DEEP_LINK_KEY, deepLink);
}

export async function consumePendingDeepLink() {
  const deepLink = await getSecureItem(PENDING_DEEP_LINK_KEY);
  if (deepLink) {
    await deleteSecureItem(PENDING_DEEP_LINK_KEY);
    return deepLink;
  }
  return null;
}
