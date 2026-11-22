export type ChannelSelection = {
  workspaceId: string;
  channelType: string;
  channelId: string;
  name: string;
};

/** 恢复店铺选择时必须校验它仍属于当前工作区。 */
export function parseChannelSelection(
  raw: string | null | undefined,
  workspaceId: string | null | undefined,
): ChannelSelection | null {
  if (!raw || !workspaceId) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<ChannelSelection>;
    if (
      parsed.workspaceId !== workspaceId ||
      !parsed.channelType ||
      !parsed.channelId
    ) {
      return null;
    }
    return {
      workspaceId,
      channelType: String(parsed.channelType),
      channelId: String(parsed.channelId),
      name: String(parsed.name || ""),
    };
  } catch {
    return null;
  }
}
