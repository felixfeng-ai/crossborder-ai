import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  PREVIEW_MODE,
  getBootstrap,
  getAgentControl,
  getDailyPlan,
  getImageAssets,
  getCommerceStores,
  getAgentTurn,
  getNotifications,
  getNotificationPreferences,
  getTimeline,
  getWorkItem,
  linkCustomerOrder,
  regenerateGeneratedMedia,
  saveGeneratedMediaToLibrary,
  saveReplyDraft,
  setAgentPaused,
  submitAgentTurn,
  submitWorkItemCommand,
  takeoverCustomerThread,
  updateNotificationPreferences,
} from "./client";
import {
  getPreviewBootstrap,
  getPreviewDailyPlan,
  getPreviewAgentTurn,
  getPreviewNotifications,
  getPreviewTimeline,
  getPreviewWorkItem,
  previewCommand,
} from "./preview";
import type {
  CommerceStore,
  NotificationItem,
  NotificationPreferences,
} from "./types";
import { currentTimeZone } from "@/features/time/timezone";
import type { ChannelSelection } from "@/features/commerce/channel-selection";

export function useBootstrapQuery(token: string | null) {
  return useQuery({
    queryKey: ["mobile", "bootstrap", token],
    enabled: Boolean(token),
    staleTime: 30_000,
    queryFn: async () =>
      PREVIEW_MODE ? getPreviewBootstrap() : await getBootstrap(token!),
  });
}

export function useAgentControlQuery(
  token: string | null,
  workspaceId: string | null,
) {
  return useQuery({
    queryKey: ["mobile", "agent-control", workspaceId],
    enabled: Boolean(token && workspaceId),
    staleTime: 15_000,
    queryFn: async () => {
      if (PREVIEW_MODE) {
        return {
          paused: false,
          frozen_action_count: 0,
          policies: [],
        };
      }
      return getAgentControl(token!, workspaceId!);
    },
  });
}

export function useSetAgentPausedMutation(
  token: string | null,
  workspaceId: string | null,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (paused: boolean) => {
      if (PREVIEW_MODE) {
        return {
          paused,
          frozen_action_count: paused ? 1 : 0,
          policies: [],
        };
      }
      return setAgentPaused(token!, workspaceId!, paused);
    },
    onSuccess: async (data) => {
      queryClient.setQueryData(
        ["mobile", "agent-control", workspaceId],
        data,
      );
      await queryClient.invalidateQueries({
        queryKey: ["mobile", "timeline", workspaceId],
      });
    },
  });
}

export function useTimelineQuery(
  token: string | null,
  workspaceId: string | null,
  channel?: ChannelSelection | null,
) {
  return useQuery({
    queryKey: [
      "mobile",
      "timeline",
      workspaceId,
      channel?.channelType,
      channel?.channelId,
    ],
    enabled: Boolean(token && workspaceId),
    staleTime: 10_000,
    // SSE 断线时仍保留低频回退刷新，避免任务状态永久停留在旧版本。
    refetchInterval: PREVIEW_MODE ? false : 15_000,
    queryFn: async () =>
      PREVIEW_MODE
        ? getPreviewTimeline()
        : await getTimeline(
            token!,
            workspaceId!,
            undefined,
            currentTimeZone(),
            channel?.channelType,
            channel?.channelId,
          ),
  });
}

export function useWorkItemQuery(
  token: string | null,
  workspaceId: string | null,
  workItemId: string,
) {
  return useQuery({
    queryKey: ["mobile", "work-item", workspaceId, workItemId],
    enabled: Boolean(token && workspaceId && workItemId),
    staleTime: 5_000,
    refetchInterval: PREVIEW_MODE ? false : 10_000,
    queryFn: async () =>
      PREVIEW_MODE
        ? getPreviewWorkItem(workItemId)
        : await getWorkItem(token!, workspaceId!, workItemId),
  });
}

export function useDailyPlanQuery(
  token: string | null,
  workspaceId: string | null,
  channel?: ChannelSelection | null,
) {
  return useQuery({
    queryKey: [
      "mobile",
      "daily-plan",
      workspaceId,
      channel?.channelType,
      channel?.channelId,
    ],
    enabled: Boolean(token && workspaceId),
    staleTime: 30_000,
    refetchInterval: PREVIEW_MODE ? false : 60_000,
    queryFn: async () =>
      PREVIEW_MODE
        ? getPreviewDailyPlan()
        : await getDailyPlan(
            token!,
            workspaceId!,
            currentTimeZone(),
            channel?.channelType,
            channel?.channelId,
          ),
  });
}

export function useNotificationsQuery(
  token: string | null,
  workspaceId: string | null,
  channel?: ChannelSelection | null,
) {
  return useQuery({
    queryKey: [
      "mobile",
      "notifications",
      workspaceId,
      channel?.channelType,
      channel?.channelId,
    ],
    enabled: Boolean(token && workspaceId),
    staleTime: 15_000,
    refetchInterval: PREVIEW_MODE ? false : 30_000,
    queryFn: async () => {
      if (PREVIEW_MODE) {
        // 预览里用 ?empty=1 / ?loading=1 造空态与加载态，方便逐页对照截图。
        const search =
          (globalThis as { location?: { search?: string } }).location?.search ??
          "";
        if (/[?&]empty=1/.test(search)) return [];
        if (/[?&]loading=1/.test(search)) {
          return new Promise<NotificationItem[]>(() => {});
        }
        return getPreviewNotifications();
      }
      return getNotifications(
        token!,
        workspaceId!,
        channel?.channelType,
        channel?.channelId,
      );
    },
  });
}

export function useCommerceStoresQuery(
  token: string | null,
  workspaceId: string | null,
) {
  return useQuery({
    queryKey: ["mobile", "commerce-stores", workspaceId],
    enabled: Boolean(token && workspaceId),
    staleTime: 60_000,
    queryFn: async () => {
      if (PREVIEW_MODE) {
        return [
          {
            channel_type: "shopify",
            channel_id: "preview-shopify",
            name: "Felix Store",
            status: "active",
          },
          {
            channel_type: "amazon",
            channel_id: "preview-amazon",
            name: "Amazon US",
            status: "active",
          },
        ] satisfies CommerceStore[];
      }
      return getCommerceStores(token!, workspaceId!);
    },
  });
}

export function useImageAssetsQuery(
  token: string | null,
  workspaceId: string | null,
) {
  return useQuery({
    queryKey: ["mobile", "image-assets", workspaceId],
    enabled: Boolean(token && workspaceId),
    staleTime: 15_000,
    queryFn: async () => {
      if (PREVIEW_MODE) return [];
      return getImageAssets(token!, workspaceId!);
    },
  });
}

export function useNotificationPreferencesQuery(
  token: string | null,
  workspaceId: string | null,
) {
  return useQuery({
    queryKey: ["mobile", "notification-preferences", workspaceId],
    enabled: Boolean(token && workspaceId),
    staleTime: 30_000,
    queryFn: async () => {
      if (PREVIEW_MODE) {
        return {
          morning_brief: true,
          day_closeout: true,
          needs_action: true,
          action_failed: true,
          authorization_expired: true,
          quiet_start_hour: 22,
          quiet_end_hour: 8,
          timezone: "Asia/Shanghai",
        } satisfies NotificationPreferences;
      }
      return getNotificationPreferences(token!, workspaceId!);
    },
  });
}

export function useUpdateNotificationPreferencesMutation(
  token: string | null,
  workspaceId: string | null,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<NotificationPreferences>) => {
      if (PREVIEW_MODE) {
        const current =
          queryClient.getQueryData<NotificationPreferences>([
            "mobile",
            "notification-preferences",
            workspaceId,
          ]);
        return { ...(current as NotificationPreferences), ...payload };
      }
      return updateNotificationPreferences(token!, workspaceId!, payload);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(
        ["mobile", "notification-preferences", workspaceId],
        data,
      );
    },
  });
}

export function useAgentTurnQuery(
  token: string | null,
  workspaceId: string | null,
  turnId: string,
) {
  return useQuery({
    queryKey: ["mobile", "agent-turn", workspaceId, turnId],
    enabled: Boolean(token && workspaceId && turnId),
    staleTime: 1_000,
    refetchInterval: PREVIEW_MODE ? false : 3_000,
    queryFn: async () =>
      PREVIEW_MODE
        ? getPreviewAgentTurn(turnId)
        : await getAgentTurn(token!, workspaceId!, turnId),
  });
}

export function useConfirmWorkItemMutation(
  token: string | null,
  workspaceId: string | null,
  workItemId: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      action: "confirm" | "choose" | "input" | "retry";
      actionId: string;
      expectedVersion: number;
      payload?: Record<string, unknown>;
      idempotencyKey: string;
    }) => {
      if (PREVIEW_MODE) return previewCommand();
      return submitWorkItemCommand(
        token!,
        workspaceId!,
        workItemId,
        {
          action: input.action,
          action_id: input.actionId,
          expected_version: input.expectedVersion,
          payload: input.payload ?? {},
        },
        input.idempotencyKey,
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["mobile", "timeline", workspaceId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["mobile", "work-item", workspaceId, workItemId],
      });
    },
  });
}

export function useSubmitAgentTurnMutation(
  token: string | null,
  workspaceId: string | null,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      input_type: "text" | "voice" | "image" | "link";
      text?: string;
      source_url?: string;
      asset_ids?: string[];
      audio_asset_id?: string;
      work_item_id?: string;
      idempotencyKey: string;
    }) => {
      if (PREVIEW_MODE) {
        await new Promise((resolve) => setTimeout(resolve, 350));
        return {
          agent_turn_id: "55555555-5555-4555-8555-555555555555",
          status: "pending",
          created_work_item_ids: [
            "11111111-1111-4111-8111-111111111111",
          ],
          stream_url: null,
          contract_version: "1",
        };
      }
      const { idempotencyKey, ...payload } = input;
      return submitAgentTurn(
        token!,
        workspaceId!,
        payload,
        idempotencyKey,
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["mobile", "timeline", workspaceId],
      });
    },
  });
}

export function useSaveGeneratedMediaMutation(
  token: string | null,
  workspaceId: string | null,
  workItemId: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      if (PREVIEW_MODE) {
        return { asset_ids: ["aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"] };
      }
      return saveGeneratedMediaToLibrary(token!, workspaceId!, workItemId);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["mobile", "image-assets", workspaceId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["mobile", "work-item", workspaceId, workItemId],
      });
    },
  });
}

export function useRegenerateGeneratedMediaMutation(
  token: string | null,
  workspaceId: string | null,
  workItemId: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      expectedVersion: number;
      prompt: string;
      referenceAssetIds: string[];
      idempotencyKey: string;
    }) => {
      if (PREVIEW_MODE) {
        return {
          action_run_id: "preview-regenerate",
          status: "queued",
          work_item_version: input.expectedVersion + 1,
        };
      }
      return regenerateGeneratedMedia(
        token!,
        workspaceId!,
        workItemId,
        {
          expected_version: input.expectedVersion,
          prompt: input.prompt,
          reference_asset_ids: input.referenceAssetIds,
        },
        input.idempotencyKey,
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["mobile", "work-item", workspaceId, workItemId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["mobile", "timeline", workspaceId],
      });
    },
  });
}

export function useSaveReplyDraftMutation(
  token: string | null,
  workspaceId: string | null,
  workItemId: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      threadId: string;
      mode: "edit" | "translate";
      bodyText?: string;
      sellerInstruction?: string;
      language?: string;
      targetLanguage?: string;
    }) => {
      if (PREVIEW_MODE) {
        await new Promise((resolve) => setTimeout(resolve, 300));
        return {
          id: "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa",
          thread_id: input.threadId,
          version: 2,
          language: input.targetLanguage ?? "en",
          source_language: input.mode === "translate" ? "zh" : null,
          body_text:
            input.bodyText ??
            "Your parcel is expected to arrive within two days.",
          status: "ready",
        };
      }
      return saveReplyDraft(token!, workspaceId!, input.threadId, {
        mode: input.mode,
        body_text: input.bodyText,
        seller_instruction: input.sellerInstruction,
        language: input.language,
        target_language: input.targetLanguage,
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["mobile", "work-item", workspaceId, workItemId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["mobile", "timeline", workspaceId],
      });
    },
  });
}

export function useTakeoverCustomerThreadMutation(
  token: string | null,
  workspaceId: string | null,
  workItemId: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (threadId: string) => {
      if (PREVIEW_MODE) {
        return {
          thread_id: threadId,
          assigned_user_id: "preview-user",
          assigned_to_me: true,
          status: "waiting_user",
          priority: "urgent",
        };
      }
      return takeoverCustomerThread(token!, workspaceId!, threadId);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["mobile", "work-item", workspaceId, workItemId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["mobile", "timeline", workspaceId],
      });
    },
  });
}

export function useLinkCustomerOrderMutation(
  token: string | null,
  workspaceId: string | null,
  workItemId: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      threadId: string;
      shopifyChannelId: string;
      externalOrderId: string;
    }) => {
      if (PREVIEW_MODE) {
        return {
          status: "linked",
          order: {
            order_name: "#1001",
            financial_status: "paid",
            fulfillment_status: "fulfilled",
            tracking_company: "UPS",
            tracking_number: "1Z999",
            tracking_url: "https://tracking.example.com/1Z999",
          },
          work_item_status: "running",
          requires_action: "none",
        };
      }
      return linkCustomerOrder(
        token!,
        workspaceId!,
        input.threadId,
        {
          shopify_channel_id: input.shopifyChannelId,
          external_order_id: input.externalOrderId,
        },
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["mobile", "work-item", workspaceId, workItemId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["mobile", "timeline", workspaceId],
      });
    },
  });
}
