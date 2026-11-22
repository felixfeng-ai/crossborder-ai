import { router, Redirect, type Href } from "expo-router";
import {
  CalendarDays,
  Check,
  ChevronDown,
  ChevronRight,
  LayoutGrid,
  Plus,
  Store,
} from "lucide-react-native";
import type { ImagePickerAsset } from "expo-image-picker";
import { useEffect, useState } from "react";
import {
  Alert,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import {
  useBootstrapQuery,
  useCommerceStoresQuery,
  useDailyPlanQuery,
  useSubmitAgentTurnMutation,
  useTimelineQuery,
} from "@/api/queries";
import {
  PREVIEW_MODE,
  transcribeVoiceAsset,
  uploadImageAsset,
} from "@/api/client";
import type { TimelineItem } from "@/api/types";
import {
  Composer,
  type AudioRecordingAsset,
} from "@/components/Composer";
import { GreetingHeader } from "@/components/GreetingHeader";
import { PageLoader } from "@/components/PageLoader";
import { PrimaryTaskCard } from "@/components/PrimaryTaskCard";
import { QuietTaskRow } from "@/components/QuietTaskRow";
import { formatGreetingName } from "@/features/account/display-name";
import { storeStatusLabel } from "@/features/stores/providers";
import { untilHour } from "@/features/time/relative";
import {
  colors,
  fonts,
  radii,
  spacing,
  type as typeScale,
} from "@/design/tokens";
import { useAuthStore } from "@/stores/auth";
import { useAgentComposerStore } from "@/stores/agentComposer";
import { useWorkspaceStore } from "@/stores/workspace";

function formatDate() {
  const date = new Date();
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  return `${date.getMonth() + 1}月${date.getDate()}日 · ${
    weekdays[date.getDay()]
  }`;
}

function createIdempotencyKey(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const token = useAuthStore((state) => state.token);
  const hydrated = useAuthStore((state) => state.hydrated);
  const activeWorkspaceId = useWorkspaceStore(
    (state) => state.activeWorkspaceId,
  );
  const setActiveWorkspace = useWorkspaceStore(
    (state) => state.setActiveWorkspace,
  );
  const activeChannel = useWorkspaceStore((state) => state.activeChannel);
  const setActiveChannel = useWorkspaceStore(
    (state) => state.setActiveChannel,
  );
  const composerDraft = useAgentComposerStore((state) => state.draft);
  const consumeComposerDraft = useAgentComposerStore(
    (state) => state.consumeDraft,
  );
  const effectiveToken = PREVIEW_MODE ? "preview" : token;

  const bootstrap = useBootstrapQuery(effectiveToken);
  const workspace =
    bootstrap.data?.workspaces.find(
      (item) => item.id === activeWorkspaceId,
    ) ?? bootstrap.data?.workspaces[0];
  const workspaceId = workspace?.id ?? null;
  const timeline = useTimelineQuery(
    effectiveToken,
    workspaceId,
    activeChannel,
  );
  const dailyPlan = useDailyPlanQuery(
    effectiveToken,
    workspaceId,
    activeChannel,
  );
  const commerceStores = useCommerceStoresQuery(effectiveToken, workspaceId);
  const sendTurn = useSubmitAgentTurnMutation(effectiveToken, workspaceId);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [voiceProcessing, setVoiceProcessing] = useState(false);
  const [storePickerOpen, setStorePickerOpen] = useState(false);

  useEffect(() => {
    if (workspace && workspace.id !== activeWorkspaceId) {
      void setActiveWorkspace(workspace);
    }
  }, [activeWorkspaceId, setActiveWorkspace, workspace]);

  if (!hydrated && !PREVIEW_MODE) return <PageLoader />;
  if (!effectiveToken) return <Redirect href="/sign-in" />;
  if (bootstrap.isLoading) return <PageLoader />;

  const items = timeline.data?.items ?? [];
  const waiting = items
    .filter((item) => item.requires_action !== "none")
    .sort((a, b) => {
      const rank = (priority: string) =>
        priority === "urgent" ? 0 : priority === "attention" ? 1 : 2;
      return rank(a.priority) - rank(b.priority);
    });
  const primary = waiting[0];
  const quiet = waiting.slice(1, 3);
  const completed = items.filter((item) => item.status === "succeeded");
  const countdown = untilHour(20);

  const openItem = (item: TimelineItem) => {
    router.push({
      pathname: "/task/[workItemId]",
      params: {
        workItemId: item.id,
        workspaceId: workspaceId ?? "",
      },
    });
  };

  const sendText = async (text: string) => {
    try {
      const isLink = /^https?:\/\/\S+$/i.test(text.trim());
      const turn = await sendTurn.mutateAsync({
        input_type: isLink ? "link" : "text",
        text: isLink ? undefined : text,
        source_url: isLink ? text : undefined,
        idempotencyKey: createIdempotencyKey("turn"),
      });
      router.push({
        pathname: "/agent/[turnId]",
        params: {
          turnId: turn.agent_turn_id,
          workspaceId: workspaceId ?? "",
          workItemId: turn.created_work_item_ids[0] ?? "",
        },
      });
    } catch {
      Alert.alert("发送失败", "网络恢复后重试，不会重复创建任务。");
    }
  };

  const sendImage = async (asset: ImagePickerAsset) => {
    if (!workspaceId || !effectiveToken || uploadingImage) return;
    setUploadingImage(true);
    try {
      const assetId = PREVIEW_MODE
        ? "66666666-6666-4666-8666-666666666666"
        : (
            await uploadImageAsset(effectiveToken, workspaceId, {
              uri: asset.uri,
              name: asset.fileName ?? "agent-image.jpg",
              type: asset.mimeType ?? "image/jpeg",
              file: asset.file,
            })
          ).id;
      const turn = await sendTurn.mutateAsync({
        input_type: "image",
        asset_ids: [assetId],
        idempotencyKey: createIdempotencyKey("image"),
      });
      router.push({
        pathname: "/agent/[turnId]",
        params: {
          turnId: turn.agent_turn_id,
          workspaceId: workspaceId ?? "",
          workItemId: turn.created_work_item_ids[0] ?? "",
        },
      });
    } catch {
      Alert.alert("图片发送失败", "请检查网络后重试，已上传素材不会重复扣费。");
    } finally {
      setUploadingImage(false);
    }
  };

  const sendVoice = async (asset: AudioRecordingAsset) => {
    if (!workspaceId || !effectiveToken || voiceProcessing) return;
    setVoiceProcessing(true);
    try {
      const transcription = PREVIEW_MODE
        ? {
            asset_id: "77777777-7777-4777-8777-777777777777",
            transcript: "帮我看看今天的订单，有超时的先处理",
          }
        : await transcribeVoiceAsset(
            effectiveToken,
            workspaceId,
            {
              uri: asset.uri,
              name: asset.name,
              type: asset.type,
              durationMs: asset.durationMs,
              file: asset.file,
            },
            createIdempotencyKey("voice-asset"),
          );
      const turn = await sendTurn.mutateAsync({
        input_type: "voice",
        text: transcription.transcript,
        audio_asset_id: transcription.asset_id,
        idempotencyKey: createIdempotencyKey("voice"),
      });
      router.push({
        pathname: "/agent/[turnId]",
        params: {
          turnId: turn.agent_turn_id,
          workspaceId: workspaceId ?? "",
          workItemId: turn.created_work_item_ids[0] ?? "",
        },
      });
    } finally {
      setVoiceProcessing(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.flex}
      >
        <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
          <View style={styles.dateRow}>
            <Text style={styles.date}>{formatDate()}</Text>
            <View style={styles.dateActions}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="选择店铺"
                onPress={() => setStorePickerOpen(true)}
                style={({ pressed }) => [
                  styles.storeRow,
                  pressed && styles.functionButtonPressed,
                ]}
              >
                <Text style={styles.store} numberOfLines={1}>
                  {activeChannel?.name || "全部店铺"}
                </Text>
                <ChevronDown
                  color={colors.faint}
                  size={14}
                  strokeWidth={2}
                />
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="打开全部功能"
                hitSlop={2}
                onPress={() => router.push("/functions")}
                style={({ pressed }) => [
                  styles.functionButton,
                  pressed && styles.functionButtonPressed,
                ]}
              >
                <LayoutGrid
                  color={colors.inkSoft}
                  size={18}
                  strokeWidth={1.7}
                />
              </Pressable>
            </View>
          </View>
          <GreetingHeader
            displayName={formatGreetingName(
              bootstrap.data?.display_name ?? "Felix",
            )}
            onOpenNotifications={() => router.push("/activity")}
          />
        </View>

        <ScrollView
          style={styles.body}
          contentContainerStyle={[
            styles.content,
            { paddingBottom: 116 + insets.bottom },
          ]}
          showsVerticalScrollIndicator={false}
        >
          {timeline.isError && (
            <View style={styles.notice}>
              <Text style={styles.noticeTitle}>暂时无法同步</Text>
              <Text style={styles.noticeText}>
                已保留最后一次结果，恢复网络后会继续同步。
              </Text>
            </View>
          )}

          {dailyPlan.data && (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="查看今日计划"
              onPress={() => router.push("/plan")}
              style={({ pressed }) => [
                styles.planRow,
                pressed && styles.planRowPressed,
              ]}
            >
              <View style={styles.planIcon}>
                <CalendarDays
                  color={colors.mutedStrong}
                  size={17}
                  strokeWidth={1.7}
                />
              </View>
              <Text style={styles.planText} numberOfLines={1}>
                <Text style={styles.planLabel}>今日计划</Text>
                {" · "}
                {dailyPlan.data.decision_count > 0
                  ? `${dailyPlan.data.decision_count} 件待你决定`
                  : dailyPlan.data.overview}
              </Text>
              <ChevronRight color={colors.muted} size={18} strokeWidth={1.8} />
            </Pressable>
          )}

          {primary ? (
            <PrimaryTaskCard item={primary} onPress={() => openItem(primary)} />
          ) : (
            <View style={styles.empty}>
              <Text style={styles.emptyTitle}>今天还没有需要你处理的事</Text>
              <Text style={styles.emptyText}>
                可以直接告诉 Agent 要铺货、查订单或回复客户。
              </Text>
            </View>
          )}

          {quiet.length > 0 && (
            <View style={styles.quietList}>
              {quiet.map((item, index) => (
                <QuietTaskRow
                  key={item.id}
                  title={item.title}
                  detail={item.summary}
                  kind={item.kind}
                  occurredAt={item.occurred_at}
                  thumbnails={item.commerce?.thumbnails}
                  last={index === quiet.length - 1}
                  onPress={() => openItem(item)}
                />
              ))}
            </View>
          )}

          {/* 「已完成」必须和待办分开：混成一条流水，用户就看不出哪些还需要他动手。 */}
          {completed.length > 0 && (
            <View style={styles.completed}>
              <Text style={styles.sectionLabel}>Agent 已完成</Text>
              {completed.slice(0, 2).map((item, index) => (
                <QuietTaskRow
                  key={item.id}
                  title={item.title}
                  detail={item.summary}
                  kind={item.kind}
                  occurredAt={item.occurred_at}
                  last={index === Math.min(completed.length, 2) - 1}
                  onPress={() => openItem(item)}
                />
              ))}
            </View>
          )}

          <View style={styles.dayEnd}>
            <View style={styles.dayEndDot} />
            <View style={styles.dayEndCopy}>
              <Text style={styles.dayEndTime}>20:00 今晚整理日结</Text>
              <Text style={styles.dayEndText}>
                Agent 整理一天的结果和明日计划
              </Text>
            </View>
            {countdown ? (
              <Text style={styles.dayEndCountdown}>{countdown}</Text>
            ) : null}
          </View>
        </ScrollView>

        <View
          style={[
            styles.composerWrap,
            { paddingBottom: Math.max(insets.bottom, 10) },
          ]}
        >
          <Composer
            sending={sendTurn.isPending || uploadingImage || voiceProcessing}
            voiceProcessing={voiceProcessing}
            onSendText={sendText}
            onPickedImage={sendImage}
            onRecorded={sendVoice}
            draft={composerDraft}
            onDraftApplied={consumeComposerDraft}
          />
        </View>
      </KeyboardAvoidingView>

      <Modal
        transparent
        visible={storePickerOpen}
        animationType="slide"
        onRequestClose={() => setStorePickerOpen(false)}
      >
        <Pressable
          style={styles.storeBackdrop}
          onPress={() => setStorePickerOpen(false)}
        />
        <SafeAreaView style={styles.storeSheet} edges={["bottom"]}>
          <View style={styles.storeHandle} />
          <Text style={styles.storeSheetTitle}>选择店铺</Text>
          <Text style={styles.storeSheetText}>
            时间线、计划、通知和功能数量会同步按店铺过滤。
          </Text>
          <View style={styles.storeList}>
            <StoreOption
              selected={!activeChannel}
              title="全部店铺"
              detail="包含所有店铺及历史未归因任务"
              onPress={() => {
                void setActiveChannel(null);
                setStorePickerOpen(false);
              }}
            />
            {commerceStores.data?.map((store) => {
              const selected =
                activeChannel?.channelType === store.channel_type &&
                activeChannel?.channelId === store.channel_id;
              return (
                <StoreOption
                  key={`${store.channel_type}:${store.channel_id}`}
                  selected={selected}
                  title={store.name}
                  detail={`${store.channel_type.toUpperCase()} · ${storeStatusLabel(store.status)}`}
                  onPress={() => {
                    if (!workspaceId) return;
                    void setActiveChannel({
                      workspaceId,
                      channelType: store.channel_type,
                      channelId: store.channel_id,
                      name: store.name,
                    });
                    setStorePickerOpen(false);
                  }}
                />
              );
            })}
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="添加店铺"
            onPress={() => {
              setStorePickerOpen(false);
              router.push("/stores" as Href);
            }}
            style={({ pressed }) => [
              styles.addStoreRow,
              pressed && styles.functionButtonPressed,
            ]}
          >
            <View style={styles.addStoreIcon}>
              <Store color={colors.inkSoft} size={17} strokeWidth={1.8} />
              <View style={styles.addStorePlus}>
                <Plus color={colors.white} size={10} strokeWidth={2.2} />
              </View>
            </View>
            <View style={styles.addStoreCopy}>
              <Text style={styles.addStoreTitle}>添加店铺</Text>
              <Text style={styles.addStoreText}>连接 Shopify、Amazon 或 Temu</Text>
            </View>
            <ChevronRight color={colors.faint} size={16} strokeWidth={2} />
          </Pressable>
          {commerceStores.isError && (
            <Text style={styles.storeError}>
              店铺列表暂时无法同步，请稍后重试。
            </Text>
          )}
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

function StoreOption({
  selected,
  title,
  detail,
  onPress,
}: {
  selected: boolean;
  title: string;
  detail: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      accessibilityLabel={`选择店铺 ${title}`}
      onPress={onPress}
      style={({ pressed }) => [
        styles.storeOption,
        selected && styles.storeOptionSelected,
        pressed && styles.functionButtonPressed,
      ]}
    >
      <View style={styles.storeOptionCopy}>
        <Text style={styles.storeOptionTitle}>{title}</Text>
        <Text style={styles.storeOptionDetail}>{detail}</Text>
      </View>
      {selected && (
        <View style={styles.storeCheck}>
          <Check color={colors.white} size={12} strokeWidth={2.2} />
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  // 状态栏与页头由 ModalScreenHeader 铺白，页面根只负责灰底。
  safe: {
    flex: 1,
    backgroundColor: colors.background,
  },
  body: {
    flex: 1,
    backgroundColor: colors.background,
  },
  flex: {
    flex: 1,
  },
  header: {
    paddingHorizontal: 22,
    backgroundColor: colors.card,
  },
  dateRow: {
    minHeight: 44,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.x4,
    marginBottom: 4,
  },
  date: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  storeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 2,
  },
  store: {
    color: colors.mutedStrong,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  dateActions: {
    flexDirection: "row",
    alignItems: "center",
    gap: 2,
  },
  functionButton: {
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 22,
  },
  functionButtonPressed: {
    backgroundColor: colors.surfaceQuiet,
  },
  content: {
    paddingHorizontal: 22,
    paddingTop: 0,
  },
  // 「不可撤销」「需要处理」是警示不是错误，用琥珀而不是危险红。
  notice: {
    marginTop: 8,
    padding: 14,
    borderRadius: radii.medium,
    backgroundColor: colors.amber,
  },
  noticeTitle: {
    color: colors.amberInk,
    fontFamily: fonts.semibold,
    fontSize: 13,
  },
  noticeText: {
    marginTop: 3,
    color: colors.amberInk,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 18,
  },
  empty: {
    marginTop: spacing.x5,
    paddingVertical: 34,
    paddingHorizontal: 22,
    borderRadius: radii.large,
    backgroundColor: colors.surface,
  },
  planRow: {
    minHeight: 44,
    marginTop: 4,
    marginBottom: 8,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  planRowPressed: {
    opacity: 0.55,
  },
  // 首页这一行是「入口」不是「状态」，图标不配底色和描边。
  planIcon: {
    width: 20,
    height: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  planText: {
    flex: 1,
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 13,
    lineHeight: 19,
  },
  planLabel: {
    color: colors.mutedStrong,
    fontFamily: fonts.semibold,
  },
  emptyTitle: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 18,
    lineHeight: 25,
  },
  emptyText: {
    marginTop: 8,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 13,
    lineHeight: 21,
  },
  quietList: {
    marginTop: 4,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
  },
  completed: {
    marginTop: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
  },
  sectionLabel: {
    paddingTop: 8,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  dayEnd: {
    minHeight: 46,
    marginTop: 2,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  dayEndDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: colors.gray,
    backgroundColor: colors.white,
  },
  dayEndCopy: {
    flex: 1,
    gap: 2,
  },
  dayEndTime: {
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 15,
    lineHeight: 21,
    fontVariant: ["tabular-nums"],
  },
  dayEndText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 13,
    lineHeight: 18,
  },
  dayEndCountdown: {
    color: colors.faint,
    fontFamily: fonts.inter,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
  },
  storeBackdrop: {
    flex: 1,
    backgroundColor: "rgba(10, 13, 18, 0.24)",
  },
  storeSheet: {
    paddingHorizontal: 22,
    paddingTop: 10,
    paddingBottom: 12,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    backgroundColor: colors.white,
  },
  storeHandle: {
    width: 38,
    height: 4,
    alignSelf: "center",
    borderRadius: 2,
    backgroundColor: colors.cardBorder,
  },
  storeSheetTitle: {
    marginTop: 22,
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 22,
    lineHeight: 30,
  },
  storeSheetText: {
    marginTop: 8,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 19,
  },
  storeList: {
    marginTop: 16,
    gap: 8,
  },
  addStoreRow: {
    minHeight: 64,
    marginTop: 10,
    paddingHorizontal: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderRadius: radii.small,
    backgroundColor: colors.surface,
  },
  addStoreIcon: {
    width: 34,
    height: 34,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 17,
    backgroundColor: colors.card,
  },
  addStorePlus: {
    position: "absolute",
    right: -2,
    bottom: -2,
    width: 16,
    height: 16,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 8,
    backgroundColor: colors.black,
  },
  addStoreCopy: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
  addStoreTitle: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: typeScale.body,
    lineHeight: 20,
  },
  addStoreText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 17,
  },
  storeOption: {
    minHeight: 62,
    paddingHorizontal: 14,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: radii.small,
    backgroundColor: colors.card,
  },
  storeOptionSelected: {
    borderColor: colors.ink,
  },
  storeOptionCopy: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
  storeOptionTitle: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 14,
    lineHeight: 20,
  },
  storeOptionDetail: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 11,
    lineHeight: 17,
  },
  storeCheck: {
    width: 22,
    height: 22,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 11,
    backgroundColor: colors.ink,
  },
  storeError: {
    marginTop: 10,
    color: colors.danger,
    fontFamily: fonts.medium,
    fontSize: 11,
    lineHeight: 17,
  },
  composerWrap: {
    position: "absolute",
    right: 0,
    bottom: 0,
    left: 0,
    backgroundColor: colors.background,
  },
});
