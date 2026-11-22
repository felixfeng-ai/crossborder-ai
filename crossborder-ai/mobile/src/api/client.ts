import Constants from "expo-constants";
import { Platform } from "react-native";

import type {
  BootstrapResponse,
  AgentControl,
  AgentTurnResponse,
  AgentTurnDetail,
  CommandResponse,
  DailyPlanResponse,
  CustomerTakeoverResponse,
  CustomerOrderSelectionResponse,
  CommerceStore,
  ImageAsset,
  ImageCategory,
  NotificationItem,
  NotificationPreferences,
  ReplyDraft,
  TimelineResponse,
  VoiceTranscriptionResponse,
  WorkItemDetail,
} from "./types";

const configuredUrl = String(
  Constants.expoConfig?.extra?.apiUrl ?? "http://127.0.0.1:8000",
).replace(/\/$/, "");

// 预览只由构建环境显式开启，生产构建不会设置此变量。
export const PREVIEW_MODE = Boolean(Constants.expoConfig?.extra?.previewMode);

function resolveBaseUrl() {
  if (Platform.OS === "android" && configuredUrl.includes("127.0.0.1")) {
    return configuredUrl.replace("127.0.0.1", "10.0.2.2");
  }
  return configuredUrl;
}

export const API_BASE_URL = resolveBaseUrl();

export type AuthTokens = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  session_id: string;
};

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
  allowRefresh = true,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  const isFormData =
    typeof FormData !== "undefined" && options.body instanceof FormData;
  if (options.body && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    if (response.status === 401 && token && allowRefresh) {
      const { useAuthStore } = await import("@/stores/auth");
      const refreshedToken = await useAuthStore
        .getState()
        .refreshSession();
      if (refreshedToken) {
        return request<T>(path, options, refreshedToken, false);
      }
    }
    let message = "请求失败，请稍后重试";
    let code: string | undefined;
    try {
      const payload = await response.json();
      message = payload.detail || payload.error?.message || message;
      code = payload.error?.code;
    } catch {
      // Keep the user-safe fallback.
    }
    throw new ApiError(message, response.status, code);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function login(email: string, password: string) {
  return request<AuthTokens>(
    "/api/v1/auth/login",
    {
      method: "POST",
      body: JSON.stringify({ email, password }),
    },
  );
}

export async function register(
  email: string,
  username: string,
  password: string,
) {
  return request<AuthTokens>(
    "/api/v1/auth/register",
    {
      method: "POST",
      body: JSON.stringify({ email, username, password }),
    },
  );
}

export async function checkUsernameAvailability(username: string) {
  return request<{ username: string; available: boolean }>(
    `/api/v1/auth/username-availability?username=${encodeURIComponent(username)}`,
  );
}

export async function refreshAuthSession(refreshToken: string) {
  return request<AuthTokens>(
    "/api/v1/auth/refresh",
    {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    },
    null,
    false,
  );
}

export async function logoutSession(token: string) {
  return request<void>(
    "/api/v1/auth/logout",
    { method: "POST" },
    token,
    false,
  );
}

export async function logoutAllSessions(token: string) {
  return request<void>(
    "/api/v1/auth/logout-all",
    { method: "POST" },
    token,
    false,
  );
}

export async function getBootstrap(token: string) {
  return request<BootstrapResponse>("/api/mobile/v1/bootstrap", {}, token);
}

export async function getTimeline(
  token: string,
  workspaceId: string,
  businessDate?: string,
  timezone?: string,
  channelType?: string,
  channelId?: string,
) {
  const query = new URLSearchParams();
  if (businessDate) query.set("date", businessDate);
  if (timezone) query.set("timezone", timezone);
  if (channelType) query.set("channel_type", channelType);
  if (channelId) query.set("channel_id", channelId);
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return request<TimelineResponse>(
    `/api/mobile/v1/workspaces/${workspaceId}/timeline${suffix}`,
    {},
    token,
  );
}

export async function getWorkItem(
  token: string,
  workspaceId: string,
  workItemId: string,
) {
  return request<WorkItemDetail>(
    `/api/mobile/v1/workspaces/${workspaceId}/work-items/${workItemId}`,
    {},
    token,
  );
}

export async function getDailyPlan(
  token: string,
  workspaceId: string,
  timezone?: string,
  channelType?: string,
  channelId?: string,
) {
  const query = new URLSearchParams();
  if (timezone) query.set("timezone", timezone);
  if (channelType) query.set("channel_type", channelType);
  if (channelId) query.set("channel_id", channelId);
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return request<DailyPlanResponse>(
    `/api/mobile/v1/workspaces/${workspaceId}/daily-plan${suffix}`,
    {},
    token,
  );
}

export async function getAgentTurn(
  token: string,
  workspaceId: string,
  turnId: string,
) {
  return request<AgentTurnDetail>(
    `/api/mobile/v1/workspaces/${workspaceId}/agent-turns/${turnId}`,
    {},
    token,
  );
}

export async function getAgentControl(
  token: string,
  workspaceId: string,
) {
  return request<AgentControl>(
    `/api/mobile/v1/workspaces/${workspaceId}/agent-control`,
    {},
    token,
  );
}

export async function setAgentPaused(
  token: string,
  workspaceId: string,
  paused: boolean,
) {
  return request<AgentControl>(
    `/api/mobile/v1/workspaces/${workspaceId}/agent-control`,
    {
      method: "PATCH",
      body: JSON.stringify({ paused }),
    },
    token,
  );
}

export async function registerDevice(
  token: string,
  payload: {
    expo_push_token: string;
    platform: "ios" | "android" | "web";
    device_name?: string;
  },
) {
  return request<{ id: string; status: string }>(
    "/api/mobile/v1/devices",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export async function getNotifications(
  token: string,
  workspaceId: string,
  channelType?: string,
  channelId?: string,
) {
  const query = new URLSearchParams();
  if (channelType) query.set("channel_type", channelType);
  if (channelId) query.set("channel_id", channelId);
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return request<NotificationItem[]>(
    `/api/mobile/v1/workspaces/${workspaceId}/notifications${suffix}`,
    {},
    token,
  );
}

export async function getCommerceStores(
  token: string,
  workspaceId: string,
) {
  return request<CommerceStore[]>(
    `/api/mobile/v1/workspaces/${workspaceId}/commerce-stores`,
    {},
    token,
  );
}

export async function getNotificationPreferences(
  token: string,
  workspaceId: string,
) {
  return request<NotificationPreferences>(
    `/api/mobile/v1/workspaces/${workspaceId}/notification-preferences`,
    {},
    token,
  );
}

export async function updateNotificationPreferences(
  token: string,
  workspaceId: string,
  payload: Partial<NotificationPreferences>,
) {
  return request<NotificationPreferences>(
    `/api/mobile/v1/workspaces/${workspaceId}/notification-preferences`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export async function markAllNotificationsRead(
  token: string,
  workspaceId: string,
) {
  return request<{ marked: number; read_at: string }>(
    `/api/mobile/v1/workspaces/${workspaceId}/notifications/read-all`,
    { method: "POST" },
    token,
  );
}

export async function markNotificationRead(
  token: string,
  workspaceId: string,
  notificationId: string,
) {
  return request<{ id: string; read_at: string }>(
    `/api/mobile/v1/workspaces/${workspaceId}/notifications/${notificationId}/read`,
    { method: "POST" },
    token,
  );
}

export async function submitWorkItemCommand(
  token: string,
  workspaceId: string,
  workItemId: string,
  payload: {
    action: "confirm" | "choose" | "input" | "retry";
    action_id: string;
    expected_version: number;
    payload: Record<string, unknown>;
  },
  idempotencyKey: string,
) {
  return request<CommandResponse>(
    `/api/mobile/v1/workspaces/${workspaceId}/work-items/${workItemId}/commands`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export async function saveGeneratedMediaToLibrary(
  token: string,
  workspaceId: string,
  workItemId: string,
) {
  return request<{ asset_ids: string[] }>(
    `/api/mobile/v1/workspaces/${workspaceId}/work-items/${workItemId}/media/save-to-library`,
    { method: "POST" },
    token,
  );
}

export async function regenerateGeneratedMedia(
  token: string,
  workspaceId: string,
  workItemId: string,
  payload: {
    expected_version: number;
    prompt: string;
    reference_asset_ids: string[];
  },
  idempotencyKey: string,
) {
  return request<{
    action_run_id: string;
    status: string;
    work_item_version: number;
  }>(
    `/api/mobile/v1/workspaces/${workspaceId}/work-items/${workItemId}/media/regenerate`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export async function submitAgentTurn(
  token: string,
  workspaceId: string,
  payload: {
    input_type: "text" | "voice" | "image" | "link";
    text?: string;
    source_url?: string;
    asset_ids?: string[];
    audio_asset_id?: string;
    work_item_id?: string;
  },
  idempotencyKey: string,
) {
  return request<AgentTurnResponse>(
    `/api/mobile/v1/workspaces/${workspaceId}/agent-turns`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export async function saveReplyDraft(
  token: string,
  workspaceId: string,
  threadId: string,
  payload: {
    mode: "edit" | "translate";
    body_text?: string;
    seller_instruction?: string;
    language?: string;
    target_language?: string;
  },
) {
  return request<ReplyDraft>(
    `/api/mobile/v1/workspaces/${workspaceId}/customer-threads/${threadId}/reply-drafts`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export async function takeoverCustomerThread(
  token: string,
  workspaceId: string,
  threadId: string,
) {
  return request<CustomerTakeoverResponse>(
    `/api/mobile/v1/workspaces/${workspaceId}/customer-threads/${threadId}/takeover`,
    { method: "POST" },
    token,
  );
}

export async function linkCustomerOrder(
  token: string,
  workspaceId: string,
  threadId: string,
  payload: {
    shopify_channel_id: string;
    external_order_id: string;
  },
) {
  return request<CustomerOrderSelectionResponse>(
    `/api/mobile/v1/workspaces/${workspaceId}/customer-threads/${threadId}/orders/link`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

type UploadImageSource = {
  uri: string;
  name: string;
  type: string;
  file?: unknown;
};

export async function uploadImageAsset(
  token: string,
  workspaceId: string,
  source: UploadImageSource,
) {
  const form = new FormData();
  if (source.file) {
    form.append("file", source.file as Blob);
  } else {
    // React Native 的 FormData 使用 uri 读取原生文件，Web 端则走 File。
    form.append(
      "file",
      {
        uri: source.uri,
        name: source.name,
        type: source.type,
      } as unknown as Blob,
    );
  }
  return request<ImageAsset>(
    `/api/mobile/v1/workspaces/${workspaceId}/assets/images`,
    {
      method: "POST",
      body: form,
    },
    token,
  );
}

export async function getImageAssets(
  token: string,
  workspaceId: string,
  category?: ImageCategory,
) {
  const query = category ? `?category=${category}` : "";
  return request<ImageAsset[]>(
    `/api/mobile/v1/workspaces/${workspaceId}/assets/images${query}`,
    {},
    token,
  );
}

export async function updateImageAssetCategory(
  token: string,
  workspaceId: string,
  assetId: string,
  category: ImageCategory,
) {
  return request<ImageAsset>(
    `/api/mobile/v1/workspaces/${workspaceId}/assets/images/${assetId}/category`,
    {
      method: "PATCH",
      body: JSON.stringify({ category }),
    },
    token,
  );
}

export type FeedbackTicketInput = {
  type: "bug" | "feature" | "billing" | "content" | "performance" | "other";
  title: string;
  content: string;
  page_path?: string;
  page_title?: string;
  browser_info?: Record<string, unknown>;
};

export type FeedbackTicket = {
  id: string;
  type: string;
  title: string;
  content: string;
  page_path: string;
  page_title: string;
  status: string;
  priority: string;
  created_at: string;
};

// 站内工单：移动端的「联系支持」走平台自己的反馈通道，不跳外部客服。
export async function createFeedback(
  token: string,
  payload: FeedbackTicketInput,
) {
  return request<FeedbackTicket>(
    "/api/v1/feedback",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export async function reorderImageAssets(
  token: string,
  workspaceId: string,
  assetIds: string[],
) {
  return request<ImageAsset[]>(
    `/api/mobile/v1/workspaces/${workspaceId}/assets/images/reorder`,
    {
      method: "PUT",
      body: JSON.stringify({ asset_ids: assetIds }),
    },
    token,
  );
}

export async function deleteImageAsset(
  token: string,
  workspaceId: string,
  assetId: string,
) {
  return request<{ deleted: boolean }>(
    `/api/mobile/v1/workspaces/${workspaceId}/assets/images/${assetId}`,
    { method: "DELETE" },
    token,
  );
}

export async function replaceImageAsset(
  token: string,
  workspaceId: string,
  assetId: string,
  source: UploadImageSource,
) {
  const form = new FormData();
  if (source.file) {
    form.append("file", source.file as Blob);
  } else {
    form.append(
      "file",
      {
        uri: source.uri,
        name: source.name,
        type: source.type,
      } as unknown as Blob,
    );
  }
  return request<ImageAsset>(
    `/api/mobile/v1/workspaces/${workspaceId}/assets/images/${assetId}/replace`,
    {
      method: "POST",
      body: form,
    },
    token,
  );
}

type UploadAudioSource = {
  uri: string;
  name: string;
  type: string;
  durationMs: number;
  file?: unknown;
};

export async function transcribeVoiceAsset(
  token: string,
  workspaceId: string,
  source: UploadAudioSource,
  idempotencyKey: string,
) {
  const form = new FormData();
  form.append("duration_ms", String(Math.max(0, Math.round(source.durationMs))));
  if (source.file) {
    form.append("file", source.file as Blob);
  } else if (Platform.OS === "web") {
    const audioResponse = await fetch(source.uri);
    if (!audioResponse.ok) {
      throw new ApiError("无法读取录制的语音", 0);
    }
    form.append("file", await audioResponse.blob(), source.name);
  } else {
    form.append(
      "file",
      {
        uri: source.uri,
        name: source.name,
        type: source.type,
      } as unknown as Blob,
    );
  }
  return request<VoiceTranscriptionResponse>(
    `/api/mobile/v1/workspaces/${workspaceId}/audio/transcriptions`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: form,
    },
    token,
  );
}
