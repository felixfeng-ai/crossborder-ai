const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export type AppDeepLink =
  | { kind: "task"; workItemId: string; workspaceId?: string }
  | { kind: "plan" | "activity"; workspaceId?: string };

function validUuid(value: string | null | undefined) {
  const normalized = String(value || "").trim();
  return UUID_PATTERN.test(normalized) ? normalized : undefined;
}

/** 只接受 App 已知路由，并过滤不可信工作区参数。 */
export function parseAppDeepLink(value: string): AppDeepLink | null {
  let url: URL;
  try {
    url = new URL(value, "https://veyaship.local");
  } catch {
    return null;
  }
  const parts = url.pathname.split("/").filter(Boolean);
  const workspaceId = validUuid(url.searchParams.get("workspaceId"));
  if (parts[0] === "t" && parts[1]) {
    const workItemId = validUuid(decodeURIComponent(parts[1]));
    if (!workItemId) return null;
    return workspaceId
      ? { kind: "task", workItemId, workspaceId }
      : { kind: "task", workItemId };
  }
  if (parts[0] === "plan" && parts.length === 1) {
    return workspaceId
      ? { kind: "plan", workspaceId }
      : { kind: "plan" };
  }
  if (parts[0] === "activity" && parts.length === 1) {
    return workspaceId
      ? { kind: "activity", workspaceId }
      : { kind: "activity" };
  }
  return null;
}
