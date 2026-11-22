import { router, useLocalSearchParams, type Href } from "expo-router";
import {
  Activity,
  Check,
  ChevronRight,
  Clock3,
  Copy,
  Download,
  ExternalLink,
  Paperclip,
  Pencil,
  Play,
  ShieldAlert,
  Truck,
  UserCheck,
} from "lucide-react-native";
import { Image } from "expo-image";
import { useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Clipboard,
  Linking,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { API_BASE_URL, PREVIEW_MODE, createFeedback } from "@/api/client";
import {
  useConfirmWorkItemMutation,
  useLinkCustomerOrderMutation,
  useImageAssetsQuery,
  useRegenerateGeneratedMediaMutation,
  useSaveGeneratedMediaMutation,
  useSaveReplyDraftMutation,
  useTakeoverCustomerThreadMutation,
  useWorkItemQuery,
} from "@/api/queries";
import type { TimelineCommerce, WorkItemDetail } from "@/api/types";
import { PageLoader } from "@/components/PageLoader";
import { IconWell } from "@/components/IconWell";
import { ModalScreenHeader } from "@/components/ModalScreenHeader";
import { QueryErrorState } from "@/components/QueryErrorState";
import { colors, fonts, radii } from "@/design/tokens";
import { commerceLabel } from "@/features/commerce/labels";
import {
  customerIntentLabel,
  customerRiskLabel,
} from "@/features/customer/risk-labels";
import { resolveQueryState } from "@/features/query-state/query-state";
import {
  saveVideoToDevice,
  videoSaveErrorMessage,
} from "@/features/media/native-video-save";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";

function idempotencyKey() {
  return `command-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function mediaUrl(value: string) {
  return /^https?:\/\//i.test(value) ? value : `${API_BASE_URL}${value}`;
}

// 生成结果按顺序固定为 主图 / 场景图 / 细节图，超出三张时回落到序号。
const MEDIA_LABELS = ["主图", "场景图", "细节图"];

function copyMediaUrl(value: string, kind: "image" | "video") {
  Clipboard.setString(mediaUrl(value));
  Alert.alert(
    "链接已复制",
    kind === "video"
      ? "视频链接为短期访问地址，请在 10 分钟内使用。"
      : "可以发送给团队或粘贴到素材工具。",
  );
}

function describeActionStatus(status: string) {
  const labels: Record<string, string> = {
    planned: "执行方案已准备",
    awaiting_confirmation: "等待你确认",
    queued: "已排队，等待执行",
    preflight: "正在检查执行条件",
    executing: "正在执行平台动作",
    verifying: "正在回读平台结果",
    succeeded: "已完成并核验",
    completed: "已完成并核验",
    blocked: "回读未通过，可重试",
    retryable_failed: "执行失败，可重试",
    cancelled: "已取消",
    compensated: "已生成补偿记录",
  };
  return labels[status] ?? "Agent 正在处理";
}

function describeOrder(
  order: NonNullable<
    NonNullable<WorkItemDetail["customer_context"]>["order"]
  >,
) {
  const labels: Record<string, string> = {
    paid: "已付款",
    pending: "待付款",
    refunded: "已退款",
    partially_refunded: "部分退款",
    fulfilled: "已发货",
    partial: "部分发货",
    unshipped: "待发货",
  };
  return [
    order.order_name,
    order.financial_status
      ? labels[order.financial_status] ?? order.financial_status
      : null,
    order.fulfillment_status
      ? labels[order.fulfillment_status] ?? order.fulfillment_status
      : null,
    order.tracking_number
      ? `${order.tracking_company ? `${order.tracking_company} ` : ""}${order.tracking_number}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function describeCandidate(
  candidate: NonNullable<
    WorkItemDetail["customer_context"]
  >["order_candidates"][number],
) {
  const head =
    [candidate.order_name, candidate.product_title]
      .filter(Boolean)
      .join(" ") || candidate.external_order_id;
  const amount = candidate.total_price
    ? [candidate.currency, candidate.total_price].filter(Boolean).join(" ")
    : null;
  const createdAt = candidate.order_created_at
    ? new Date(candidate.order_created_at)
    : null;
  const created =
    createdAt && !Number.isNaN(createdAt.getTime())
      ? `${createdAt.getMonth() + 1}月${createdAt.getDate()}日下单`
      : null;
  return { head, tail: [amount, created].filter(Boolean).join(" · ") };
}

export default function WorkItemScreen() {
  const params = useLocalSearchParams<{
    workItemId: string;
    workspaceId?: string;
  }>();
  const token = useAuthStore((state) => state.token);
  const storedWorkspaceId = useWorkspaceStore(
    (state) => state.activeWorkspaceId,
  );
  const workspaceId = params.workspaceId || storedWorkspaceId;
  const workItemId =
    typeof params.workItemId === "string" ? params.workItemId : "";
  const effectiveToken = PREVIEW_MODE ? "preview" : token;
  const detail = useWorkItemQuery(effectiveToken, workspaceId, workItemId);
  const mutation = useConfirmWorkItemMutation(
    effectiveToken,
    workspaceId,
    workItemId,
  );
  const draftMutation = useSaveReplyDraftMutation(
    effectiveToken,
    workspaceId,
    workItemId,
  );
  const takeoverMutation = useTakeoverCustomerThreadMutation(
    effectiveToken,
    workspaceId,
    workItemId,
  );
  const linkOrderMutation = useLinkCustomerOrderMutation(
    effectiveToken,
    workspaceId,
    workItemId,
  );
  const saveMediaMutation = useSaveGeneratedMediaMutation(
    effectiveToken,
    workspaceId,
    workItemId,
  );
  const regenerateMediaMutation = useRegenerateGeneratedMediaMutation(
    effectiveToken,
    workspaceId,
    workItemId,
  );
  const imageAssets = useImageAssetsQuery(effectiveToken, workspaceId);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [draftOpen, setDraftOpen] = useState(false);
  const [draftMode, setDraftMode] = useState<"edit" | "translate">("edit");
  const [draftValue, setDraftValue] = useState("");
  const [instruction, setInstruction] = useState("");
  const [selectingOrderId, setSelectingOrderId] = useState<string | null>(
    null,
  );
  const [pickedOrderId, setPickedOrderId] = useState<string | null>(null);
  const [attachmentPreview, setAttachmentPreview] = useState<{
    url: string;
    name: string;
  } | null>(null);
  const [attachmentImageFailed, setAttachmentImageFailed] =
    useState(false);
  const [supportPending, setSupportPending] = useState(false);
  const [savingVideo, setSavingVideo] = useState(false);
  const [regenerateOpen, setRegenerateOpen] = useState(false);
  const [regeneratePrompt, setRegeneratePrompt] = useState("");
  const [referenceAssetIds, setReferenceAssetIds] = useState<string[]>([]);
  const [referenceExpanded, setReferenceExpanded] = useState(false);
  const pendingKey = useRef("");
  const regenerateKey = useRef("");

  const mediaImages = detail.data?.media_result?.images ?? [];
  const queryState = resolveQueryState({
    isLoading: detail.isLoading,
    isError: detail.isError,
    hasData: Boolean(detail.data),
  });

  if (queryState === "loading") return <PageLoader />;
  if (queryState === "error") {
    return (
      <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
        <ModalScreenHeader
          title="Agent 任务"
          onBack={() => router.back()}
        />
        <QueryErrorState
          title="任务暂时无法同步"
          description="当前没有把网络失败当成任务失效，请恢复网络后重试。"
          onRetry={() => void detail.refetch()}
        />
      </SafeAreaView>
    );
  }
  if (!detail.data) {
    return (
      <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
        <View style={styles.missing}>
          <Text style={styles.missingTitle}>这件事已经处理或已失效</Text>
          <Pressable onPress={() => router.back()} style={styles.backAction}>
            <Text style={styles.backActionText}>返回时间线</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  const item = detail.data;
  const action = item.available_actions[0];
  const latestAction = item.action_runs[item.action_runs.length - 1];
  const orderCandidates = item.customer_context?.order_candidates ?? [];
  const isOrderSelection =
    item.requires_action === "choose" && orderCandidates.length > 0;
  const resultSummary =
    typeof item.result?.summary === "string" ? item.result.summary : null;
  // 完成态「结果」卡：result.orders 由执行侧写入，缺失时整卡降级不渲染。
  const rawOrders = Array.isArray(item.result?.orders)
    ? item.result.orders
    : [];
  const completedOrders = rawOrders
    .filter((entry): entry is Record<string, unknown> => !!entry)
    .map((entry) => ({
      orderName:
        typeof entry.order_name === "string" ? entry.order_name : null,
      product: typeof entry.product === "string" ? entry.product : null,
      status: typeof entry.status === "string" ? entry.status : null,
    }));
  const resultAmount =
    typeof item.result?.amount === "string" ? item.result.amount : null;
  const resultCurrency =
    typeof item.result?.currency === "string" ? item.result.currency : null;
  const displayTitle =
    item.status === "completed" && item.title.includes("\n")
      ? `${item.title.split("\n")[0]}\n已处理`
      : item.title;
  const displayStep =
    item.status === "completed" && !item.current_step.includes("核验")
      ? `${item.current_step}并核验`
      : item.current_step;
  // 金额与单数走同一条 commerce 文案，和首页黑卡、计划页保持同一说法。
  const detailCommerce =
    (item.result?.commerce as TimelineCommerce | undefined) ?? null;
  const commerceText = detailCommerce ? commerceLabel(detailCommerce) : "";
  // 失败态在详情页有两处独立信号：任务本身失败，或素材任务失败。
  const detailFailed =
    item.status === "failed" ||
    item.status === "error" ||
    item.media_result?.task_status === "failed";
  const actionPreview = item.action_preview;
  const isMediaRetry = Boolean(item.media_result?.can_retry && action);
  const actionLabel = isMediaRetry ? "重新生成" : action?.label;
  // 产物已生成且任务没失败 → 走"重新生成 / 保存到素材库"双按钮；
  // 没有可执行动作的已完成任务 → 只留归档说明，不再给按钮。
  const isMediaSuccess = mediaImages.length > 0 && !detailFailed;
  // 素材失败按稿走「发生了什么 / 可以怎么做」两张卡，不显示通用信息卡。
  const isMediaFailure =
    detailFailed && item.media_result?.media_type === "image";
  const isArchived = !action && item.status === "completed";
  const confirmCopy = isMediaRetry
    ? {
        title: "重新生成这份素材",
        body: "Agent 会保留当前任务记录，使用同一份商品信息和生成要求重新提交，完成后回写新的结果。",
        confirm: "开始重新生成",
        progress: "已重新提交，新的结果会回写到这个任务。",
      }
    : {
        title: actionLabel ?? "确认执行",
        body: "Agent 会执行这项操作并回读平台结果。执行计划和影响范围以当前任务为准。",
        confirm: "确认执行",
        progress: "正在执行，结果会回写原任务。",
      };

  const openMediaRegenerate = (showReferences = false) => {
    setRegeneratePrompt(item.media_result?.prompt ?? "");
    setReferenceAssetIds(
      item.media_result?.reference_assets.map((asset) => asset.id) ?? [],
    );
    setReferenceExpanded(showReferences);
    setRegenerateOpen(true);
  };

  const submitMediaRegenerate = async () => {
    const prompt = regeneratePrompt.trim();
    if (prompt.length < 5 || regenerateMediaMutation.isPending) {
      Alert.alert("描述太短", "请至少输入 5 个字符的商品图描述。");
      return;
    }
    if (!regenerateKey.current) {
      regenerateKey.current = idempotencyKey();
    }
    try {
      await regenerateMediaMutation.mutateAsync({
        expectedVersion: item.version,
        prompt,
        referenceAssetIds,
        idempotencyKey: regenerateKey.current,
      });
      regenerateKey.current = "";
      setRegenerateOpen(false);
      Alert.alert("已重新提交", "新的结果会回写到这个任务，旧结果仍保留。");
    } catch {
      Alert.alert("没有提交", "请刷新任务状态后重试。");
    }
  };

  const toggleReference = (assetId: string) => {
    setReferenceAssetIds((current) => {
      if (current.includes(assetId)) {
        return current.filter((id) => id !== assetId);
      }
      if (current.length >= 4) {
        Alert.alert("最多选择 4 张参考图");
        return current;
      }
      return [...current, assetId];
    });
  };

  const saveVideo = async (url: string) => {
    if (savingVideo) return;
    setSavingVideo(true);
    try {
      await saveVideoToDevice(mediaUrl(url));
      Alert.alert("已保存到相册", "视频已经写入系统相册。");
    } catch (reason) {
      Alert.alert("没有保存", videoSaveErrorMessage(reason));
    } finally {
      setSavingVideo(false);
    }
  };

  // 「联系支持」走站内工单：带上任务编号、错误信息与页面路径，不跳外部客服。
  const sendSupportTicket = async () => {
    if (supportPending) return;
    if (PREVIEW_MODE) {
      Alert.alert(
        "已提交给平台",
        "预览模式不会真的建工单。真机上会写入平台工单并返回单号。",
      );
      return;
    }
    setSupportPending(true);
    try {
      const ticket = await createFeedback(effectiveToken!, {
        type: "bug",
        title: `素材生成失败：${item.title}`.slice(0, 200),
        content: [
          `任务 ${workItemId} 的素材生成失败。`,
          item.media_result?.error
            ? `错误信息：${item.media_result.error}`
            : "错误信息：平台未返回具体原因。",
          resultSummary ? `结果摘要：${resultSummary}` : "",
        ]
          .filter(Boolean)
          .join("\n")
          .slice(0, 5000),
        page_path: `/task/${workItemId}`,
        page_title: item.title.slice(0, 200),
        browser_info: { source: "mobile-app", platform: "expo" },
      });
      Alert.alert(
        "已提交给平台",
        `工单 ${ticket.id.slice(0, 8).toUpperCase()} 已记录，处理进展会回到当前账号。`,
      );
    } catch {
      Alert.alert("没有提交成功", "网络恢复后再点一次，不会重复建单。");
    } finally {
      setSupportPending(false);
    }
  };

  const confirm = async () => {
    if (!action || mutation.isPending) return;
    if (!pendingKey.current) pendingKey.current = idempotencyKey();
    try {
      await mutation.mutateAsync({
        action: action.kind,
        actionId: action.id,
        expectedVersion: item.version,
        idempotencyKey: pendingKey.current,
      });
      pendingKey.current = "";
      setConfirmOpen(false);
      Alert.alert("已交给 Agent", confirmCopy.progress);
    } catch {
      Alert.alert("没有执行", "任务可能已被其他人处理，请刷新后再试。");
    }
  };

  const saveDraft = async () => {
    if (!item.customer_context || draftMutation.isPending) return;
    const value =
      draftMode === "edit" ? draftValue.trim() : instruction.trim();
    if (!value) return;
    try {
      await draftMutation.mutateAsync({
        threadId: item.customer_context.thread_id,
        mode: draftMode,
        bodyText: draftMode === "edit" ? value : undefined,
        sellerInstruction: draftMode === "translate" ? value : undefined,
        language: item.customer_context.language ?? undefined,
      });
      setDraftOpen(false);
      setInstruction("");
      Alert.alert("草稿已更新", "已生成新版本，请确认后发送。");
    } catch {
      Alert.alert("没有保存", "草稿未更新，请稍后重试。");
    }
  };

  const takeOverCustomerThread = async () => {
    if (!item.customer_context || takeoverMutation.isPending) return;
    try {
      await takeoverMutation.mutateAsync(
        item.customer_context.thread_id,
      );
      Alert.alert("已由你接管", "Agent 已停止这项会话的自动回复。");
    } catch {
      Alert.alert("没有接管", "会话可能已被其他人处理，请刷新后再试。");
    }
  };

  const selectOrder = async (
    candidate: (typeof orderCandidates)[number],
  ) => {
    if (
      !item.customer_context ||
      !candidate.shopify_channel_id ||
      linkOrderMutation.isPending
    ) {
      return;
    }
    setSelectingOrderId(candidate.external_order_id);
    try {
      await linkOrderMutation.mutateAsync({
        threadId: item.customer_context.thread_id,
        shopifyChannelId: candidate.shopify_channel_id,
        externalOrderId: candidate.external_order_id,
      });
      Alert.alert("订单已选择", "Agent 正在使用这单的真实物流信息生成回复。");
    } catch {
      Alert.alert("没有关联", "订单可能已变化，请刷新后重新选择。");
    } finally {
      setSelectingOrderId(null);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
      <ModalScreenHeader
        title="Agent 任务"
        onBack={() => router.back()}
      />

      <View style={styles.body}>
        <ScrollView
          style={styles.body}
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
        >
        <View style={styles.stepRow}>
          <View
            style={[
              styles.stepDot,
              {
                backgroundColor: detailFailed
                  ? colors.danger
                  : item.status === "waiting_user"
                    ? colors.amberDot
                    : colors.green,
              },
            ]}
          />
          <Text style={styles.stepText}>{displayStep}</Text>
        </View>
        <Text style={styles.title}>{displayTitle}</Text>
        <Text style={styles.summary}>
          {item.status === "completed" && resultSummary
            ? resultSummary
            : item.summary}
        </Text>
        {commerceText ? (
          <Text style={styles.commerce}>{commerceText}</Text>
        ) : null}
        {!isMediaFailure && latestAction?.policy_reason && (
          <Text style={styles.policyReason}>
            {latestAction.requires_dual_approval
              ? `${latestAction.policy_reason} · 需双人确认`
              : latestAction.policy_reason}
          </Text>
        )}

        {item.customer_context?.customer_message && (
          <View style={styles.customerCard}>
            <View style={styles.customerHeader}>
              <Text style={styles.customerLabel}>客户原话</Text>
              <View style={styles.customerRisk}>
                {item.customer_context.risk_level === "high" ? (
                  <ShieldAlert
                    color={colors.danger}
                    size={12}
                    strokeWidth={1.8}
                  />
                ) : null}
                <Text
                  style={[
                    styles.customerRiskText,
                    item.customer_context.risk_level === "high" &&
                      styles.customerRiskTextHigh,
                  ]}
                >
                  {customerIntentLabel(item.customer_context.intent)}
                  {" · "}
                  {customerRiskLabel(
                    item.customer_context.risk_level,
                  )}
                </Text>
              </View>
            </View>
            <Text style={styles.customerText}>
              {item.customer_context.customer_message}
            </Text>
            {item.customer_context.attachments.length > 0 && (
              <View style={styles.attachmentList}>
                {item.customer_context.attachments.map((attachment) => {
                  const isImage = attachment.content_type.startsWith(
                    "image/",
                  );
                  return (
                    <Pressable
                      key={attachment.id}
                      accessibilityRole={isImage ? "imagebutton" : "text"}
                      accessibilityLabel={`附件 ${attachment.file_name}`}
                      disabled={!isImage}
                      onPress={() =>
                        {
                          setAttachmentImageFailed(false);
                          setAttachmentPreview({
                            url: attachment.url,
                            name: attachment.file_name,
                          });
                        }
                      }
                      style={({ pressed }) => [
                        styles.attachmentChip,
                        pressed && styles.pressed,
                      ]}
                    >
                      <Paperclip
                        color={colors.muted}
                        size={13}
                        strokeWidth={1.7}
                      />
                      <Text
                        style={styles.attachmentName}
                        numberOfLines={1}
                      >
                        {attachment.file_name}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            )}
            {orderCandidates.length > 0 && (
              <View style={styles.orderChoiceList}>
                <Text style={styles.orderChoiceLabel}>候选订单</Text>
                {orderCandidates.map((candidate) => (
                  <Pressable
                    key={`${candidate.shopify_channel_id}-${candidate.external_order_id}`}
                    accessibilityRole="button"
                    accessibilityLabel={`选择订单 ${candidate.order_name ?? candidate.external_order_id}`}
                    disabled={
                      linkOrderMutation.isPending ||
                      !candidate.shopify_channel_id
                    }
                    onPress={() => setPickedOrderId(candidate.external_order_id)}
                    style={({ pressed }) => [
                      styles.orderChoice,
                      pickedOrderId === candidate.external_order_id &&
                        styles.orderChoicePicked,
                      pressed && styles.pressed,
                    ]}
                  >
                    <View style={styles.orderChoiceCopy}>
                      <Text style={styles.orderChoiceText} numberOfLines={1}>
                        {describeCandidate(candidate).head}
                      </Text>
                      {describeCandidate(candidate).tail ? (
                        <Text style={styles.orderChoiceMeta} numberOfLines={1}>
                          {describeCandidate(candidate).tail}
                        </Text>
                      ) : null}
                    </View>
                    {selectingOrderId === candidate.external_order_id ? (
                      <ActivityIndicator
                        color={colors.muted}
                        size="small"
                      />
                    ) : pickedOrderId === candidate.external_order_id ? (
                      <View style={styles.orderCheckOn}>
                        <Check
                          color={colors.white}
                          size={13}
                          strokeWidth={2.2}
                        />
                      </View>
                    ) : (
                      <View style={styles.orderCheckOff} />
                    )}
                  </Pressable>
                ))}
              </View>
            )}
            {orderCandidates.length > 0 && (
              <View style={styles.orderPickNote}>
                <Text style={styles.orderPickNoteText}>
                  选中后，将用这条订单的物流信息生成回复草稿，并同步到店铺后台。
                </Text>
              </View>
            )}
            {item.customer_context.order && (
              <Pressable
                accessibilityRole={
                  item.customer_context.order.tracking_url
                    ? "link"
                    : "text"
                }
                disabled={!item.customer_context.order.tracking_url}
                onPress={() => {
                  const url =
                    item.customer_context?.order?.tracking_url;
                  if (url) void Linking.openURL(url);
                }}
                style={({ pressed }) => [
                  styles.orderChip,
                  pressed && styles.pressed,
                ]}
              >
                <Truck
                  color={colors.greenInk}
                  size={13}
                  strokeWidth={1.8}
                />
                <Text style={styles.orderText} numberOfLines={1}>
                  {describeOrder(item.customer_context.order)}
                </Text>
              </Pressable>
            )}
            {item.customer_context.requires_human &&
              !item.customer_context.assigned_to_me && (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="由我接管这个客户会话"
                  disabled={takeoverMutation.isPending}
                  onPress={() => void takeOverCustomerThread()}
                  style={({ pressed }) => [
                    styles.takeoverButton,
                    pressed && styles.pressed,
                  ]}
                >
                  {takeoverMutation.isPending ? (
                    <ActivityIndicator
                      color={colors.inkSoft}
                      size="small"
                    />
                  ) : (
                    <UserCheck
                      color={colors.inkSoft}
                      size={15}
                      strokeWidth={1.8}
                    />
                  )}
                  <Text style={styles.takeoverText}>由我接管</Text>
                </Pressable>
              )}
            {item.customer_context.assigned_to_me && (
              <View style={styles.assignedRow}>
                <UserCheck
                  color={colors.greenInk}
                  size={13}
                  strokeWidth={1.8}
                />
                <Text style={styles.assignedText}>已由你接管</Text>
              </View>
            )}
            {item.customer_context.draft_text && (
              <>
                <View style={styles.customerDivider} />
                <View style={styles.draftHeader}>
                  <Text style={styles.customerLabel}>Agent 草稿</Text>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="编辑回复草稿"
                    onPress={() => {
                      setDraftMode("edit");
                      setDraftValue(item.customer_context?.draft_text ?? "");
                      setDraftOpen(true);
                    }}
                    style={styles.editButton}
                  >
                    <Pencil color={colors.muted} size={14} strokeWidth={1.7} />
                    <Text style={styles.editText}>编辑</Text>
                  </Pressable>
                </View>
                <Text style={styles.draftText}>
                  {item.customer_context.draft_text}
                </Text>
              </>
            )}
          </View>
        )}

        {item.media_result?.media_type === "image" &&
          item.media_result.images.length > 0 && (
            <>
              <View style={styles.mediaHeader}>
                <Text style={styles.mediaTitle}>生成结果</Text>
                <Text style={styles.mediaCount}>
                  {item.media_result.images.length} 张
                </Text>
              </View>
              <View style={styles.mediaGrid}>
                {item.media_result.images.map((url, index) => (
                  <View key={`${url}-${index}`} style={styles.mediaCell}>
                    <Pressable
                      accessibilityRole="imagebutton"
                      accessibilityLabel={`预览第 ${index + 1} 张图片`}
                      onPress={() => void Linking.openURL(mediaUrl(url))}
                      style={({ pressed }) => [
                        styles.mediaThumb,
                        pressed && styles.pressed,
                      ]}
                    >
                      <Image
                        source={{ uri: mediaUrl(url) }}
                        style={styles.mediaThumbImage}
                        contentFit="cover"
                      />
                    </Pressable>
                    <Text style={styles.mediaThumbLabel} numberOfLines={1}>
                      {MEDIA_LABELS[index] ?? `第 ${index + 1} 张`}
                    </Text>
                  </View>
                ))}
              </View>
            </>
          )}

        {item.media_result?.media_type === "video" &&
          item.media_result.video_url && (
            <Pressable
              accessibilityRole="button"
              onPress={() =>
                void Linking.openURL(mediaUrl(item.media_result!.video_url!))
              }
              style={({ pressed }) => [
                styles.videoCard,
                pressed && styles.pressed,
              ]}
            >
              <View style={styles.videoIcon}>
                <Play color={colors.ink} size={20} strokeWidth={1.8} />
              </View>
              <View style={styles.videoCopy}>
                <Text style={styles.videoTitle}>视频已生成</Text>
                <Text style={styles.videoText}>点击预览成片</Text>
              </View>
              <ExternalLink color={colors.muted} size={18} strokeWidth={1.7} />
            </Pressable>
          )}

        {item.media_result?.media_type === "video" &&
          item.media_result.video_url && (
            <View style={styles.mediaActions} accessibilityRole="toolbar">
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="复制视频链接"
                onPress={() =>
                  copyMediaUrl(item.media_result!.video_url!, "video")
                }
                style={styles.mediaAction}
              >
                <Copy color={colors.muted} size={15} strokeWidth={1.7} />
                <Text style={styles.mediaActionText}>复制链接</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="保存视频"
                disabled={savingVideo}
                onPress={() =>
                  void saveVideo(item.media_result!.video_url!)
                }
                style={styles.mediaAction}
              >
                {savingVideo ? (
                  <ActivityIndicator color={colors.muted} size="small" />
                ) : (
                  <>
                    <Download
                      color={colors.muted}
                      size={15}
                      strokeWidth={1.7}
                    />
                    <Text style={styles.mediaActionText}>保存视频</Text>
                  </>
                )}
              </Pressable>
            </View>
          )}

        {item.media_result?.error && !isMediaFailure && (
          <View style={styles.mediaError}>
            <Text style={styles.mediaErrorText}>{item.media_result.error}</Text>
          </View>
        )}

        {isMediaFailure && (
          <>
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>发生了什么</Text>
              <Text style={styles.sectionText}>
                {item.media_result?.error ?? resultSummary ?? item.summary}
              </Text>
              <Text style={styles.sectionMeta}>
                任务 {workItemId.slice(0, 8).toUpperCase()} · 失败于{" "}
                {new Date(item.updated_at).toLocaleTimeString("zh-CN", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </Text>
            </View>
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>可以怎么做</Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="调整描述后重新生成"
                onPress={() => openMediaRegenerate(false)}
                style={({ pressed }) => [
                  styles.sectionRow,
                  pressed && styles.pressed,
                ]}
              >
                <Text style={styles.sectionRowText}>调整描述后重新生成</Text>
                <ChevronRight
                  color={colors.faint}
                  size={16}
                  strokeWidth={1.8}
                />
              </Pressable>
              <View style={styles.sectionDivider} />
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="更换一张参考图"
                onPress={() => openMediaRegenerate(true)}
                style={({ pressed }) => [
                  styles.sectionRow,
                  pressed && styles.pressed,
                ]}
              >
                <Text style={styles.sectionRowText}>更换一张参考图</Text>
                <ChevronRight
                  color={colors.faint}
                  size={16}
                  strokeWidth={1.8}
                />
              </Pressable>
              <View style={styles.sectionDivider} />
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="联系支持协助处理"
                disabled={supportPending}
                onPress={() => void sendSupportTicket()}
                style={({ pressed }) => [
                  styles.sectionRow,
                  pressed && styles.pressed,
                ]}
              >
                <Text style={styles.sectionRowText}>联系支持协助处理</Text>
                <ChevronRight
                  color={colors.faint}
                  size={16}
                  strokeWidth={1.8}
                />
              </Pressable>
            </View>
          </>
        )}

        {item.status === "completed" && completedOrders.length > 0 && (
          <View style={styles.result}>
            <Text style={styles.sectionTitle}>结果</Text>
            {completedOrders.map((order, index) => (
              <View
                key={`${order.orderName ?? index}-${order.product ?? ""}`}
                style={[
                  styles.resultOrderRow,
                  index > 0 && styles.resultOrderRowSpaced,
                ]}
              >
                <Text style={styles.resultOrderText} numberOfLines={1}>
                  {[order.orderName, order.product]
                    .filter(Boolean)
                    .join(" - ")}
                </Text>
                <Text style={styles.resultOrderStatus}>
                  {order.status ?? "已更新"}
                </Text>
                <Check color={colors.greenInk} size={14} strokeWidth={2.2} />
              </View>
            ))}
          </View>
        )}
        {item.status === "completed" && resultAmount && (
          <Text style={styles.resultAmountNote}>
            {`金额合计 ${resultCurrency ?? ""} ${resultAmount} 已包含在订单记录中。`.replace(
              /\s+/g,
              " ",
            )}
          </Text>
        )}
        {resultSummary && !isMediaFailure && completedOrders.length === 0 && (
          <View style={styles.result}>
            <Text
              style={[
                styles.resultLabel,
                detailFailed && styles.resultLabelFailed,
              ]}
            >
              Agent 结果
            </Text>
            <Text style={styles.resultText}>{resultSummary}</Text>
          </View>
        )}

        {!isMediaFailure && (
          <View style={styles.infoCard}>
          {!isMediaSuccess && item.status !== "completed" && (
            <>
          <View style={styles.infoRow}>
            <IconWell>
              <Clock3 color={colors.muted} size={17} strokeWidth={1.7} />
            </IconWell>
            <View style={styles.infoCopy}>
              <Text style={styles.infoTitle}>时间要求</Text>
              <Text style={styles.infoText}>
                {item.due_at
                  ? new Date(item.due_at).toLocaleString("zh-CN", {
                      month: "numeric",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : "没有硬性截止时间"}
              </Text>
            </View>
          </View>
          <View style={styles.divider} />
          {latestAction && (
            <>
              <View style={styles.infoRow}>
                <IconWell>
                  <Activity color={colors.muted} size={17} strokeWidth={1.7} />
                </IconWell>
                <View style={styles.infoCopy}>
                  <Text style={styles.infoTitle}>执行进度</Text>
                  <Text style={styles.infoText}>
                    {describeActionStatus(latestAction.status)}
                    {latestAction.attempt > 0
                      ? ` · 第 ${latestAction.attempt} 次`
                      : ""}
                  </Text>
                </View>
              </View>
              <View style={styles.divider} />
            </>
          )}
            </>
          )}
          <View style={styles.infoRow}>
            <IconWell>
              <Check color={colors.muted} size={17} strokeWidth={1.7} />
            </IconWell>
            <View style={styles.infoCopy}>
              <Text style={styles.infoTitle}>
                {isMediaSuccess ? "下一步" : "接下来"}
              </Text>
              <Text style={styles.infoText}>
                {isMediaSuccess
                  ? "可直接发布到 Listing，或先存进素材库再挑。"
                  : item.status === "completed"
                    ? "无需操作 · Agent 将持续观察"
                    : actionLabel || "Agent 会继续处理并回写结果"}
              </Text>
            </View>
          </View>
        </View>
        )}
        </ScrollView>
      </View>

      {isMediaSuccess ? (
        <View style={styles.footer}>
          <View style={styles.footerButtons}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="重新生成"
              onPress={() => openMediaRegenerate(false)}
              style={({ pressed }) => [
                styles.secondary,
                pressed && styles.pressed,
              ]}
            >
              <Text style={styles.secondaryText}>重新生成</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="保存到素材库"
              disabled={saveMediaMutation.isPending}
              onPress={() => {
                saveMediaMutation.mutate(undefined, {
                  onSuccess: () => {
                    Alert.alert("已保存到素材库", "生成结果已经加入素材库。");
                    router.push("/library" as Href);
                  },
                  onError: () => {
                    Alert.alert("没有保存", "素材库没有变化，请稍后重试。");
                  },
                });
              }}
              style={({ pressed }) => [
                styles.primary,
                styles.primaryFlex,
                pressed && styles.pressed,
              ]}
            >
              {saveMediaMutation.isPending ? (
                <ActivityIndicator color={colors.white} size="small" />
              ) : (
                <Text style={styles.primaryText}>保存到素材库</Text>
              )}
            </Pressable>
          </View>
        </View>
      ) : isMediaRetry && detailFailed ? (
        <View style={styles.footer}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={actionLabel ?? "重新生成"}
            onPress={() => openMediaRegenerate(false)}
            style={({ pressed }) => [
              styles.primary,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.primaryText}>
              {actionLabel ?? "重新生成"}
            </Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="联系支持"
            disabled={supportPending}
            onPress={() => void sendSupportTicket()}
            style={({ pressed }) => [
              styles.footerLink,
              pressed && styles.pressed,
            ]}
          >
            {supportPending ? (
              <ActivityIndicator color={colors.muted} size="small" />
            ) : (
              <Text style={styles.footerLinkText}>联系支持</Text>
            )}
          </Pressable>
        </View>
      ) : isOrderSelection ? (
        <View style={styles.footer}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="用这个订单回复"
            disabled={!pickedOrderId || linkOrderMutation.isPending}
            onPress={() => {
              const candidate = orderCandidates.find(
                (entry) => entry.external_order_id === pickedOrderId,
              );
              if (candidate) void selectOrder(candidate);
            }}
            style={({ pressed }) => [
              styles.primary,
              (!pickedOrderId || linkOrderMutation.isPending) &&
                styles.primaryDisabled,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.primaryText}>
              {linkOrderMutation.isPending ? "正在同步订单…" : "用这个订单回复"}
            </Text>
          </Pressable>
        </View>
      ) : !!action ? (
        <View style={styles.footer}>
          <Pressable
            accessibilityRole="button"
            onPress={() => setConfirmOpen(true)}
            style={({ pressed }) => [
              styles.primary,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.primaryText}>{actionLabel}</Text>
          </Pressable>
          {detailFailed && (
            <Text style={styles.footerHint}>
              本次未产生费用。如果反复失败，可以把任务编号发给 VeyaShip 支持。
            </Text>
          )}
        </View>
      ) : isArchived ? (
        <Text style={styles.archived}>本次处理已归档</Text>
      ) : null}

      <Modal
        transparent
        visible={regenerateOpen}
        animationType="slide"
        onRequestClose={() => setRegenerateOpen(false)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setRegenerateOpen(false)}
        />
        <SafeAreaView style={styles.sheet} edges={["bottom"]}>
          <View style={styles.sheetHandle} />
          <Text style={styles.sheetTitle}>重新生成素材</Text>
          <Text style={styles.sheetText}>
            修改描述或参考图后会创建新的结果，原结果不会覆盖。
          </Text>
          <TextInput
            multiline
            accessibilityLabel="素材生成描述"
            onChangeText={setRegeneratePrompt}
            placeholder="描述商品、场景、光线和构图"
            placeholderTextColor={colors.faint}
            style={styles.regenerateInput}
            textAlignVertical="top"
            value={regeneratePrompt}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="选择参考图"
            onPress={() => setReferenceExpanded((value) => !value)}
            style={({ pressed }) => [
              styles.referenceToggle,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.referenceToggleText}>
              参考图 · {referenceAssetIds.length} 张
            </Text>
            <ChevronRight
              color={colors.faint}
              size={16}
              strokeWidth={1.8}
            />
          </Pressable>
          {referenceExpanded && (
            <View style={styles.referencePicker}>
              {imageAssets.isLoading ? (
                <ActivityIndicator color={colors.muted} size="small" />
              ) : imageAssets.data?.length ? (
                <ScrollView
                  horizontal
                  showsHorizontalScrollIndicator={false}
                  contentContainerStyle={styles.referenceList}
                >
                  {imageAssets.data.map((asset) => {
                    const selected = referenceAssetIds.includes(asset.id);
                    return (
                      <Pressable
                        key={asset.id}
                        accessibilityRole="button"
                        accessibilityState={{ selected }}
                        accessibilityLabel={`${selected ? "取消" : "选择"}参考图 ${asset.name}`}
                        onPress={() => toggleReference(asset.id)}
                        style={[
                          styles.referenceOption,
                          selected && styles.referenceOptionSelected,
                        ]}
                      >
                        <Image
                          source={{ uri: mediaUrl(asset.url) }}
                          style={styles.referenceImage}
                          contentFit="cover"
                        />
                        {selected && (
                          <View style={styles.referenceCheck}>
                            <Check
                              color={colors.white}
                              size={11}
                              strokeWidth={2.2}
                            />
                          </View>
                        )}
                      </Pressable>
                    );
                  })}
                </ScrollView>
              ) : (
                <Text style={styles.referenceEmpty}>
                  素材库中还没有可选参考图。
                </Text>
              )}
            </View>
          )}
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="提交重新生成"
            disabled={regenerateMediaMutation.isPending}
            onPress={() => void submitMediaRegenerate()}
            style={({ pressed }) => [
              styles.primary,
              styles.sheetPrimary,
              pressed && styles.pressed,
            ]}
          >
            {regenerateMediaMutation.isPending ? (
              <ActivityIndicator color={colors.white} size="small" />
            ) : (
              <Text style={styles.primaryText}>重新生成</Text>
            )}
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={() => setRegenerateOpen(false)}
            style={styles.cancel}
          >
            <Text style={styles.cancelText}>取消</Text>
          </Pressable>
        </SafeAreaView>
      </Modal>

      <Modal
        transparent
        visible={confirmOpen}
        animationType="slide"
        onRequestClose={() => setConfirmOpen(false)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setConfirmOpen(false)}
        />
        <SafeAreaView style={styles.sheet} edges={["bottom"]}>
          <View style={styles.sheetHandle} />
          <Text style={styles.sheetTitle}>
            {actionPreview?.title ?? confirmCopy.title}
          </Text>
          <Text style={styles.sheetText}>
            {actionPreview?.description ?? confirmCopy.body}
          </Text>
          {actionPreview && actionPreview.fields.length > 0 && (
            <View style={styles.previewFields}>
              {actionPreview.fields.map((field, index) => (
                <View
                  key={`${field.label}-${index}`}
                  style={[
                    styles.previewRow,
                    index < actionPreview.fields.length - 1 &&
                      styles.previewDivider,
                  ]}
                >
                  <Text style={styles.previewLabel}>{field.label}</Text>
                  <Text
                    style={[
                      styles.previewValue,
                      field.emphasis && styles.previewValueStrong,
                    ]}
                    numberOfLines={2}
                  >
                    {field.value}
                  </Text>
                </View>
              ))}
            </View>
          )}
          {actionPreview?.warning && (
            <View style={styles.previewWarning}>
              <Text style={styles.previewWarningText}>
                {actionPreview.warning}
              </Text>
            </View>
          )}
          <Pressable
            accessibilityRole="button"
            onPress={confirm}
            disabled={mutation.isPending}
            style={({ pressed }) => [
              styles.primary,
              styles.sheetPrimary,
              pressed && styles.pressed,
            ]}
          >
            {mutation.isPending ? (
              <ActivityIndicator color={colors.white} />
            ) : (
              <Text style={styles.primaryText}>{confirmCopy.confirm}</Text>
            )}
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={() => setConfirmOpen(false)}
            style={styles.cancel}
          >
            <Text style={styles.cancelText}>取消</Text>
          </Pressable>
        </SafeAreaView>
      </Modal>

      <Modal
        transparent
        visible={draftOpen}
        animationType="slide"
        onRequestClose={() => setDraftOpen(false)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setDraftOpen(false)}
        />
        <SafeAreaView style={styles.sheet} edges={["bottom"]}>
          <View style={styles.sheetHandle} />
          <Text style={styles.sheetTitle}>修改回复草稿</Text>
          <View style={styles.modeRow}>
            <Pressable
              onPress={() => setDraftMode("edit")}
              style={[
                styles.mode,
                draftMode === "edit" && styles.modeActive,
              ]}
            >
              <Text
                style={[
                  styles.modeText,
                  draftMode === "edit" && styles.modeTextActive,
                ]}
              >
                直接修改
              </Text>
            </Pressable>
            <Pressable
              onPress={() => setDraftMode("translate")}
              style={[
                styles.mode,
                draftMode === "translate" && styles.modeActive,
              ]}
            >
              <Text
                style={[
                  styles.modeText,
                  draftMode === "translate" && styles.modeTextActive,
                ]}
              >
                中文指令
              </Text>
            </Pressable>
          </View>
          <TextInput
            multiline
            value={draftMode === "edit" ? draftValue : instruction}
            onChangeText={
              draftMode === "edit" ? setDraftValue : setInstruction
            }
            placeholder={
              draftMode === "edit"
                ? "修改回复正文"
                : "例如：请告诉客户包裹两天内会到"
            }
            placeholderTextColor={colors.muted}
            style={styles.draftInput}
            textAlignVertical="top"
          />
          <Pressable
            accessibilityRole="button"
            onPress={saveDraft}
            disabled={draftMutation.isPending}
            style={({ pressed }) => [
              styles.primary,
              pressed && styles.pressed,
            ]}
          >
            {draftMutation.isPending ? (
              <ActivityIndicator color={colors.white} />
            ) : (
              <Text style={styles.primaryText}>保存为新版本</Text>
            )}
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={() => setDraftOpen(false)}
            style={styles.cancel}
          >
            <Text style={styles.cancelText}>取消</Text>
          </Pressable>
        </SafeAreaView>
      </Modal>

      <Modal
        animationType="fade"
        transparent
        visible={Boolean(attachmentPreview)}
        onRequestClose={() => setAttachmentPreview(null)}
      >
        <View style={styles.attachmentPreviewBackdrop}>
          <SafeAreaView style={styles.attachmentPreviewSafe}>
            <View style={styles.attachmentPreviewHeader}>
              <Text
                style={styles.attachmentPreviewTitle}
                numberOfLines={1}
              >
                {attachmentPreview?.name}
              </Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="关闭附件预览"
                onPress={() => setAttachmentPreview(null)}
                style={styles.attachmentPreviewClose}
              >
                <Text style={styles.attachmentPreviewCloseText}>关闭</Text>
              </Pressable>
            </View>
            {attachmentPreview && (
              <>
                {attachmentImageFailed ? (
                  <View style={styles.attachmentPreviewFallback}>
                    <Paperclip
                      color={colors.muted}
                      size={24}
                      strokeWidth={1.5}
                    />
                    <Text style={styles.attachmentPreviewFallbackText}>
                      这个附件暂时无法预览
                    </Text>
                  </View>
                ) : (
                  <Image
                    source={{
                      uri: /^https?:\/\//i.test(attachmentPreview.url)
                        ? attachmentPreview.url
                        : `${API_BASE_URL}${attachmentPreview.url}`,
                      headers: effectiveToken
                        ? { Authorization: `Bearer ${effectiveToken}` }
                        : undefined,
                    }}
                    style={styles.attachmentPreviewImage}
                    contentFit="contain"
                    onError={() => setAttachmentImageFailed(true)}
                  />
                )}
              </>
            )}
          </SafeAreaView>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.background,
  },
  body: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    paddingHorizontal: 22,
    paddingTop: 18,
    paddingBottom: 120,
  },
  stepRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  stepDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  stepText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  title: {
    maxWidth: 330,
    marginTop: 24,
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 30,
    lineHeight: 39,
  },
  summary: {
    maxWidth: 330,
    marginTop: 16,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 15,
    lineHeight: 25,
  },
  commerce: {
    maxWidth: 330,
    marginTop: 8,
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 15,
    fontVariant: ["tabular-nums"],
  },
  policyReason: {
    marginTop: 6,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 14,
  },
  infoCard: {
    marginTop: 32,
    paddingHorizontal: 18,
    borderRadius: radii.large,
    backgroundColor: colors.surface,
  },
  customerCard: {
    marginTop: 28,
    padding: 18,
    borderRadius: radii.large,
    backgroundColor: colors.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
  },
  customerLabel: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  customerHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
  },
  customerRisk: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  customerRiskText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  customerRiskTextHigh: {
    color: colors.danger,
  },
  draftHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  editButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingVertical: 4,
    paddingLeft: 10,
  },
  editText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  customerText: {
    marginTop: 8,
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 14,
    lineHeight: 22,
  },
  takeoverButton: {
    minHeight: 34,
    marginTop: 12,
    paddingHorizontal: 12,
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 17,
    backgroundColor: colors.white,
  },
  takeoverText: {
    color: colors.inkSoft,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  assignedRow: {
    marginTop: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
  },
  assignedText: {
    color: colors.greenInk,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  attachmentList: {
    marginTop: 11,
    gap: 6,
  },
  attachmentChip: {
    minHeight: 30,
    maxWidth: "100%",
    paddingHorizontal: 10,
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 15,
    backgroundColor: colors.white,
  },
  attachmentName: {
    maxWidth: 230,
    color: colors.inkSoft,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  orderChip: {
    minHeight: 30,
    marginTop: 8,
    maxWidth: "100%",
    paddingHorizontal: 10,
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderRadius: 15,
    backgroundColor: colors.surfaceQuiet,
  },
  orderChoiceList: {
    marginTop: 12,
    gap: 6,
  },
  orderChoiceLabel: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  orderChoice: {
    minHeight: 44,
    paddingHorizontal: 12,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    borderRadius: radii.small,
    backgroundColor: colors.card,
  },
  orderChoiceText: {
    flex: 1,
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 14,
    lineHeight: 20,
  },
  orderChoiceCopy: {
    flex: 1,
    gap: 3,
  },
  orderChoiceMeta: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 17,
  },
  orderChoicePicked: {
    borderWidth: 1.5,
    borderColor: colors.ink,
  },
  orderPickNote: {
    marginTop: 10,
    paddingHorizontal: 12,
    paddingVertical: 11,
    borderRadius: radii.small,
    backgroundColor: colors.surfaceQuiet,
  },
  orderPickNoteText: {
    color: colors.mutedStrong,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 19,
  },
  orderCheckOn: {
    width: 22,
    height: 22,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 11,
    backgroundColor: colors.ink,
  },
  orderCheckOff: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    backgroundColor: colors.card,
  },
  primaryDisabled: {
    opacity: 0.42,
  },
  orderText: {
    maxWidth: 260,
    color: colors.inkSoft,
    fontFamily: fonts.medium,
    fontSize: 13,
  },
  attachmentPreviewBackdrop: {
    flex: 1,
    padding: 16,
    justifyContent: "center",
    backgroundColor: "rgba(10, 12, 15, 0.72)",
  },
  attachmentPreviewSafe: {
    maxHeight: "88%",
    overflow: "hidden",
    borderRadius: 16,
    backgroundColor: colors.ink,
  },
  attachmentPreviewHeader: {
    minHeight: 50,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  attachmentPreviewTitle: {
    flex: 1,
    color: colors.surface,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  attachmentPreviewClose: {
    minWidth: 44,
    minHeight: 36,
    alignItems: "center",
    justifyContent: "center",
  },
  attachmentPreviewCloseText: {
    color: colors.line,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  attachmentPreviewImage: {
    width: "100%",
    minHeight: 360,
    flexShrink: 1,
  },
  attachmentPreviewFallback: {
    minHeight: 360,
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
  },
  attachmentPreviewFallbackText: {
    color: colors.faint,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  customerDivider: {
    height: StyleSheet.hairlineWidth,
    marginVertical: 16,
    backgroundColor: colors.line,
  },
  draftText: {
    marginTop: 8,
    color: colors.inkSoft,
    fontFamily: fonts.medium,
    fontSize: 14,
    lineHeight: 23,
  },
  mediaHeader: {
    marginTop: 24,
    minHeight: 20,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  mediaTitle: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 13,
  },
  mediaCount: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  mediaGrid: {
    marginTop: 10,
    flexDirection: "row",
    gap: 8,
  },
  mediaCell: {
    flex: 1,
    minWidth: 0,
    gap: 6,
  },
  mediaThumb: {
    width: "100%",
    overflow: "hidden",
    borderRadius: 12,
    backgroundColor: colors.surface,
  },
  mediaThumbImage: {
    width: "100%",
    aspectRatio: 1,
  },
  mediaThumbLabel: {
    color: colors.faint,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 16,
  },
  mediaActions: {
    minHeight: 44,
    marginTop: 6,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  mediaAction: {
    minHeight: 40,
    paddingHorizontal: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderRadius: 20,
    backgroundColor: colors.surface,
  },
  mediaActionText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  videoCard: {
    minHeight: 74,
    marginTop: 24,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderRadius: 16,
    backgroundColor: colors.surface,
  },
  videoIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.white,
  },
  videoCopy: {
    flex: 1,
    gap: 3,
  },
  videoTitle: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 13,
  },
  videoText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  mediaError: {
    marginTop: 18,
    padding: 16,
    borderRadius: 14,
    backgroundColor: colors.dangerSoft,
  },
  mediaErrorText: {
    color: colors.danger,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 19,
  },
  result: {
    marginTop: 26,
    padding: 18,
    borderRadius: radii.large,
    backgroundColor: colors.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
  },
  resultLabel: {
    color: colors.greenInk,
    fontFamily: fonts.semibold,
    fontSize: 12,
  },
  resultLabelFailed: {
    color: colors.danger,
  },
  resultText: {
    marginTop: 7,
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 15,
    lineHeight: 24,
  },
  infoRow: {
    minHeight: 82,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  infoCopy: {
    flex: 1,
    gap: 4,
  },
  infoTitle: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 15,
  },
  infoText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 18,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.line,
  },
  footer: {
    position: "absolute",
    right: 0,
    bottom: 0,
    left: 0,
    paddingHorizontal: 18,
    paddingBottom: 18,
    // 底部动作区自己铺灰，避免透出白色导航层。
    backgroundColor: colors.background,
  },
  primary: {
    minHeight: 52,
    paddingHorizontal: 20,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.black,
  },
  primaryFlex: {
    flex: 1,
  },
  primaryText: {
    color: colors.white,
    fontFamily: fonts.semibold,
    fontSize: 17,
  },
  footerButtons: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  secondary: {
    flex: 1,
    minHeight: 52,
    paddingHorizontal: 18,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    borderRadius: 14,
    backgroundColor: colors.card,
  },
  secondaryText: {
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 17,
  },
  footerHint: {
    marginTop: 10,
    color: colors.faint,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 18,
    textAlign: "center",
  },
  footerLink: {
    minHeight: 40,
    alignItems: "center",
    justifyContent: "center",
  },
  footerLinkText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 13,
  },
  sectionCard: {
    marginTop: 20,
    paddingHorizontal: 18,
    paddingVertical: 16,
    borderRadius: radii.large,
    backgroundColor: colors.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
  },
  sectionTitle: {
    marginBottom: 10,
    color: colors.mutedStrong,
    fontFamily: fonts.medium,
    fontSize: 13,
    lineHeight: 18,
  },
  sectionText: {
    color: colors.inkSoft,
    fontFamily: fonts.medium,
    fontSize: 15,
    lineHeight: 23,
  },
  sectionMeta: {
    marginTop: 10,
    color: colors.faint,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 18,
  },
  sectionRow: {
    minHeight: 46,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  sectionRowText: {
    flex: 1,
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 15,
    lineHeight: 22,
  },
  sectionDivider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.line,
  },
  resultOrderRow: {
    minHeight: 34,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  resultOrderRowSpaced: {
    marginTop: 6,
  },
  resultOrderText: {
    flex: 1,
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 14,
    lineHeight: 21,
  },
  resultOrderStatus: {
    color: colors.greenInk,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  resultAmountNote: {
    marginTop: 10,
    color: colors.faint,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 18,
  },
  archived: {
    paddingBottom: 24,
    color: colors.faint,
    fontFamily: fonts.medium,
    fontSize: 12,
    textAlign: "center",
  },
  pressed: {
    opacity: 0.84,
    transform: [{ scale: 0.99 }],
  },
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(10, 13, 18, 0.24)",
  },
  sheet: {
    paddingHorizontal: 22,
    paddingTop: 10,
    paddingBottom: 12,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    backgroundColor: colors.white,
  },
  sheetHandle: {
    width: 38,
    height: 4,
    alignSelf: "center",
    borderRadius: 2,
    backgroundColor: colors.line,
  },
  sheetTitle: {
    marginTop: 22,
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 22,
  },
  sheetText: {
    marginTop: 10,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 13,
    lineHeight: 22,
  },
  previewFields: {
    marginTop: 16,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 16,
    backgroundColor: colors.surface,
  },
  previewRow: {
    minHeight: 44,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 16,
  },
  previewDivider: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  previewLabel: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  previewValue: {
    maxWidth: "65%",
    color: colors.inkSoft,
    fontFamily: fonts.medium,
    fontSize: 12,
    textAlign: "right",
  },
  previewValueStrong: {
    color: colors.ink,
    fontFamily: fonts.semibold,
  },
  previewWarning: {
    marginTop: 12,
    padding: 12,
    borderRadius: 12,
    backgroundColor: colors.dangerSoft,
  },
  previewWarningText: {
    color: colors.danger,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 17,
  },
  regenerateInput: {
    minHeight: 112,
    marginTop: 16,
    padding: 14,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: 14,
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 14,
    lineHeight: 22,
    backgroundColor: colors.surface,
  },
  referenceToggle: {
    minHeight: 46,
    marginTop: 10,
    paddingHorizontal: 4,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  referenceToggleText: {
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 13,
  },
  referencePicker: {
    minHeight: 82,
    justifyContent: "center",
  },
  referenceList: {
    gap: 9,
    paddingVertical: 6,
  },
  referenceOption: {
    width: 72,
    height: 72,
    padding: 2,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: 12,
  },
  referenceOptionSelected: {
    borderColor: colors.ink,
  },
  referenceImage: {
    width: "100%",
    height: "100%",
    borderRadius: 9,
    backgroundColor: colors.surface,
  },
  referenceCheck: {
    position: "absolute",
    top: 5,
    right: 5,
    width: 19,
    height: 19,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 10,
    backgroundColor: colors.ink,
  },
  referenceEmpty: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 18,
  },
  sheetPrimary: {
    marginTop: 20,
  },
  modeRow: {
    marginTop: 16,
    padding: 4,
    flexDirection: "row",
    gap: 4,
    borderRadius: 12,
    backgroundColor: colors.surface,
  },
  mode: {
    flex: 1,
    minHeight: 38,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 9,
  },
  modeActive: {
    backgroundColor: colors.white,
    shadowColor: colors.ink,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
  },
  modeText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  modeTextActive: {
    color: colors.ink,
    fontFamily: fonts.semibold,
  },
  draftInput: {
    minHeight: 132,
    marginTop: 12,
    marginBottom: 18,
    padding: 14,
    borderRadius: 14,
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 14,
    lineHeight: 22,
    backgroundColor: colors.surface,
  },
  cancel: {
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 8,
  },
  cancelText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 14,
  },
  missing: {
    flex: 1,
    paddingHorizontal: 28,
    justifyContent: "center",
  },
  missingTitle: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 22,
    lineHeight: 30,
  },
  backAction: {
    minHeight: 50,
    marginTop: 24,
    borderRadius: radii.pill,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.black,
  },
  backActionText: {
    color: colors.white,
    fontFamily: fonts.semibold,
    fontSize: 14,
  },
});
