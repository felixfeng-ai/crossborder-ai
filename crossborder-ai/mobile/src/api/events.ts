import { API_BASE_URL } from "./client";

export type WorkspaceEvent = {
  event_id: string;
  type: string;
  schema_version: string;
  workspace_id: string;
  work_item_id: string | null;
  agent_turn_id: string | null;
  action_run_id: string | null;
  occurred_at: string;
  data: Record<string, unknown>;
};

type Subscription = {
  token: string;
  workspaceId: string;
  onEvent: (event: WorkspaceEvent) => void;
};

function parseFrame(frame: string): WorkspaceEvent | null {
  let id = "";
  let eventType = "";
  const dataLines: string[] = [];

  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("id:")) id = line.slice(3).trim();
    if (line.startsWith("event:")) eventType = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!eventType || dataLines.length === 0) return null;

  try {
    const payload = JSON.parse(dataLines.join("\n")) as WorkspaceEvent;
    return {
      ...payload,
      event_id: id || payload.event_id,
      type: eventType || payload.type,
    };
  } catch {
    return null;
  }
}

export function subscribeWorkspaceEvents({
  token,
  workspaceId,
  onEvent,
}: Subscription) {
  let cursor = 0;
  let stopped = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let request: XMLHttpRequest | null = null;

  const connect = () => {
    if (stopped) return;
    request = new XMLHttpRequest();
    let consumed = 0;
    let buffer = "";

    const reconnect = () => {
      if (stopped || reconnectTimer) return;
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, 1800);
    };

    request.open(
      "GET",
      `${API_BASE_URL}/api/mobile/v1/workspaces/${workspaceId}/stream?cursor=${cursor}`,
    );
    request.setRequestHeader("Accept", "text/event-stream");
    request.setRequestHeader("Authorization", `Bearer ${token}`);
    request.onprogress = () => {
      if (!request) return;
      const incoming = request.responseText.slice(consumed);
      consumed = request.responseText.length;
      buffer += incoming;
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const event = parseFrame(frame);
        if (!event) continue;
        const numericId = Number(event.event_id);
        if (Number.isSafeInteger(numericId) && numericId > cursor) {
          cursor = numericId;
        }
        onEvent(event);
      }
    };
    request.onerror = reconnect;
    request.onloadend = reconnect;
    request.send();
  };

  connect();
  return () => {
    stopped = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    request?.abort();
  };
}
