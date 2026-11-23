import { router, useLocalSearchParams } from "expo-router";
import {
  Activity,
  Check,
  ChevronRight,
  Circle,
  TriangleAlert,
} from "lucide-react-native";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { PREVIEW_MODE } from "@/api/client";
import { useAgentTurnQuery, useWorkItemQuery } from "@/api/queries";
import type { AgentStep } from "@/api/types";
import { ModalScreenHeader } from "@/components/ModalScreenHeader";
import { QueryErrorState } from "@/components/QueryErrorState";
import { colors, fonts, radii } from "@/design/tokens";
import { resolveQueryState } from "@/features/query-state/query-state";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";

function stepIcon(status: string) {
  if (status === "completed") {
    return <Check color={colors.greenInk} size={13} strokeWidth={2.2} />;
  }
  if (status === "running") {
    return <Activity color={colors.mutedStrong} size={13} strokeWidth={1.9} />;
  }
  return <Circle color={colors.faint} size={11} strokeWidth={1.7} />;
}

function stepStatusLabel(status: string) {
  if (status === "completed") return "完成";
  if (status === "running") return "进行中";
  return "待执行";
}

export default function AgentTurnScreen() {
  const params = useLocalSearchParams<{
    turnId: string;
    workspaceId?: string;
    workItemId?: string;
  }>();
  const token = useAuthStore((state) => state.token);
  const storedWorkspaceId = useWorkspaceStore(
    (state) => state.activeWorkspaceId,
  );
  const workspaceId = params.workspaceId || storedWorkspaceId;
  const turnId = typeof params.turnId === "string" ? params.turnId : "";
  const effectiveToken = PREVIEW_MODE ? "preview" : token;
  const detail = useAgentTurnQuery(effectiveToken, workspaceId, turnId);
  const item = detail.data;
  const requestedWorkItemId =
    typeof params.workItemId === "string" ? params.workItemId : "";
  const workItemId =
    requestedWorkItemId || item?.created_work_item_ids[0] || "";
  const linkedWorkItem = useWorkItemQuery(
    effectiveToken,
    workspaceId,
    workItemId,
  );
  const queryState = resolveQueryState({
    isLoading: detail.isLoading,
    isError: detail.isError,
    hasData: Boolean(detail.data),
  });

  if (queryState === "loading") {
    return (
      <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
        <View style={styles.loading}>
          <ActivityIndicator color={colors.ink} />
        </View>
      </SafeAreaView>
    );
  }
  if (queryState === "error" || !item) {
    return (
      <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
        <ModalScreenHeader title="执行结果" onBack={() => router.back()} />
        <QueryErrorState
          error={detail.error}
          title="执行结果暂时无法同步"
          description="当前不会把请求失败当成 Agent 仍在处理。"
          onRetry={() => void detail.refetch()}
        />
      </SafeAreaView>
    );
  }

  const isWorking =
    item.status === "pending" || item.status === "running";
  const completedStepCount =
    item?.steps.filter((step) => step.status === "completed").length ?? 0;
  const totalStepCount = item?.steps.length ?? 0;
  const pendingWorkCount = item?.created_work_item_ids.length ?? 0;
  const failed = item?.status === "failed";
  const resultCopy = isWorking
    ? "小 Veya 正在处理这条指令"
    : failed
      ? "这件事需要你接手"
      : item?.result_summary || "结果已经整理好，可以查看下一步。";
  const resultMeta = isWorking
    ? "进度会自动保留"
    : failed
      ? "执行没有完成，仍然保留了当前上下文"
      : [
          totalStepCount > 0 ? `${completedStepCount} 步已完成` : null,
          pendingWorkCount > 0 ? `${pendingWorkCount} 项待确认` : null,
        ]
          .filter(Boolean)
          .join(" · ");

  return (
    <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
      <ModalScreenHeader title="执行结果" onBack={() => router.back()} />

      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.receipt}>
          <View style={styles.statusLine}>
            {isWorking ? (
              <ActivityIndicator color={colors.muted} size="small" />
            ) : failed ? (
              <TriangleAlert color={colors.danger} size={12} strokeWidth={1.9} />
            ) : (
              <View style={styles.greenDot} />
            )}
            <Text
              style={[styles.statusLineText, failed && styles.statusLineTextFailed]}
            >
              {isWorking ? "处理中" : failed ? "需接手" : "已完成"}
            </Text>
          </View>

          <Text style={styles.headline} numberOfLines={3}>
            {isWorking
              ? "还在处理这条指令"
              : failed
                ? "这件事需要你接手"
                : item?.result_summary || "已经处理完，结果如下。"}
          </Text>

          {!!item?.text && (
            <Text style={styles.subcopy} numberOfLines={3}>
              {item.text}
            </Text>
          )}

          <View style={styles.resultSection}>
            <Text style={styles.sectionLabel}>执行结果</Text>
            <Text style={styles.resultText}>{resultCopy}</Text>
            {!!resultMeta && (
              <Text style={styles.resultMeta}>{resultMeta}</Text>
            )}
          </View>

          {!!item?.steps.length && (
            <View style={styles.stepsSection}>
              <View style={styles.stepsHeader}>
                <Text style={styles.sectionLabel}>执行过程</Text>
                <Text style={styles.stepsCount}>
                  {completedStepCount}/{totalStepCount}
                </Text>
              </View>
              <View style={styles.steps}>
                {item.steps.map((step: AgentStep) => (
                  <View
                    key={`${step.label}-${step.status}`}
                    style={styles.stepRow}
                  >
                    <View
                      style={[
                        styles.stepMarker,
                        step.status === "completed" &&
                          styles.stepMarkerComplete,
                        step.status === "running" &&
                          styles.stepMarkerRunning,
                      ]}
                    >
                      {stepIcon(step.status)}
                    </View>
                    <Text style={styles.stepText}>{step.label}</Text>
                    <Text
                      style={[
                        styles.stepStatus,
                        step.status === "completed" &&
                          styles.stepStatusComplete,
                        step.status === "running" &&
                          styles.stepStatusRunning,
                      ]}
                    >
                      {stepStatusLabel(step.status)}
                    </Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {item?.error && (
            <View style={styles.error}>
              <Text style={styles.errorText}>{item.error}</Text>
            </View>
          )}

          {!isWorking && workItemId && (
            <View style={styles.followUpSection}>
              <View style={styles.stepsHeader}>
                <Text style={styles.sectionLabel}>待确认事项</Text>
                <Text style={styles.stepsCount}>{pendingWorkCount}</Text>
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="打开待确认事项"
                onPress={() =>
                  router.replace({
                    pathname: "/task/[workItemId]",
                    params: {
                      workItemId,
                      workspaceId: workspaceId ?? "",
                    },
                  })
                }
                style={({ pressed }) => [
                  styles.followUpRow,
                  pressed && styles.followUpPressed,
                ]}
              >
                <View style={styles.followUpStatus} />
                <View style={styles.followUpCopy}>
                  <Text style={styles.followUpTitle} numberOfLines={2}>
                    {linkedWorkItem.data
                      ? linkedWorkItem.data.title.replace(/\n/g, " ")
                      : linkedWorkItem.isError
                        ? "处理方案暂时无法读取"
                        : "正在整理待确认事项…"}
                  </Text>
                  <Text style={styles.followUpMeta} numberOfLines={1}>
                    {linkedWorkItem.data?.current_step ||
                      "打开查看 Agent 准备的处理方案"}
                  </Text>
                </View>
                {linkedWorkItem.isLoading ? (
                  <ActivityIndicator color={colors.muted} size="small" />
                ) : (
                  <ChevronRight
                    color={colors.muted}
                    size={17}
                    strokeWidth={1.8}
                  />
                )}
              </Pressable>
            </View>
          )}
        </View>
      </ScrollView>

      {!isWorking && workItemId && (
        <View style={styles.footer}>
          <Pressable
            accessibilityRole="button"
            onPress={() =>
              router.replace({
                pathname: "/task/[workItemId]",
                params: {
                  workItemId,
                  workspaceId: workspaceId ?? "",
                },
              })
            }
            style={({ pressed }) => [
              styles.primary,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.primaryText}>查看完整记录</Text>
          </Pressable>
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  content: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 112,
  },
  receipt: {
    padding: 18,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radii.large,
    backgroundColor: colors.white,
    shadowColor: colors.ink,
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.05,
    shadowRadius: 24,
    elevation: 2,
  },
  statusLine: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  greenDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: colors.green,
  },
  statusLineText: {
    color: colors.mutedStrong,
    fontFamily: fonts.medium,
    fontSize: 13,
    lineHeight: 18,
  },
  statusLineTextFailed: {
    color: colors.danger,
  },
  headline: {
    marginTop: 10,
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 30,
    lineHeight: 38,
    letterSpacing: -0.4,
  },
  subcopy: {
    marginTop: 10,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 15,
    lineHeight: 23,
  },
  statusBadge: {
    minHeight: 26,
    paddingHorizontal: 9,
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    borderWidth: 1,
    borderColor: colors.greenSoft,
    borderRadius: radii.pill,
    backgroundColor: colors.surface,
  },
  statusBadgeWorking: {
    borderColor: colors.infoLine,
    backgroundColor: colors.infoSoft,
  },
  statusBadgeFailed: {
    borderColor: colors.dangerLine,
    backgroundColor: colors.dangerSoft,
  },
  statusBadgeText: {
    color: colors.greenInk,
    fontFamily: fonts.semibold,
    fontSize: 12,
    lineHeight: 14,
  },
  statusBadgeTextWorking: {
    color: colors.infoInk,
  },
  statusBadgeTextFailed: {
    color: colors.danger,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    marginVertical: 16,
    backgroundColor: colors.line,
  },
  command: {
    padding: 13,
    borderRadius: 14,
    backgroundColor: colors.surface,
  },
  sectionLabel: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 15,
  },
  commandText: {
    marginTop: 6,
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 14,
    lineHeight: 22,
  },
  resultSection: {
    marginTop: 22,
  },
  resultText: {
    marginTop: 9,
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 21,
    lineHeight: 32,
  },
  resultMeta: {
    marginTop: 6,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 18,
  },
  stepsSection: {
    marginTop: 22,
  },
  stepsHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  stepsCount: {
    color: colors.muted,
    fontFamily: fonts.inter,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
  },
  steps: {
    marginTop: 7,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
  },
  stepRow: {
    minHeight: 50,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  stepMarker: {
    width: 22,
    height: 22,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 11,
    backgroundColor: colors.surface,
  },
  stepMarkerComplete: {
    borderColor: colors.greenSoft,
    backgroundColor: colors.greenSoft,
  },
  stepMarkerRunning: {
    borderColor: colors.infoLine,
    backgroundColor: colors.infoSoft,
  },
  stepText: {
    flex: 1,
    minWidth: 0,
    color: colors.inkSoft,
    fontFamily: fonts.medium,
    fontSize: 13,
    lineHeight: 20,
  },
  stepStatus: {
    color: colors.faint,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 14,
  },
  stepStatusComplete: {
    color: colors.greenInk,
  },
  stepStatusRunning: {
    color: colors.infoInk,
  },
  error: {
    marginTop: 20,
    padding: 14,
    borderRadius: 14,
    backgroundColor: colors.dangerSoft,
  },
  errorText: {
    color: colors.danger,
    fontFamily: fonts.medium,
    fontSize: 13,
    lineHeight: 21,
  },
  followUpSection: {
    marginTop: 18,
  },
  followUpRow: {
    minHeight: 64,
    marginTop: 7,
    paddingHorizontal: 12,
    paddingVertical: 11,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 14,
    backgroundColor: colors.surface,
  },
  followUpPressed: {
    backgroundColor: colors.surface,
  },
  followUpStatus: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: colors.amberDot,
  },
  followUpCopy: {
    flex: 1,
    minWidth: 0,
  },
  followUpTitle: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 13,
    lineHeight: 19,
  },
  followUpMeta: {
    marginTop: 3,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 16,
  },
  footer: {
    position: "absolute",
    right: 18,
    bottom: 18,
    left: 18,
    paddingTop: 10,
    backgroundColor: colors.surface,
  },
  primary: {
    minHeight: 52,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    borderRadius: 14,
    backgroundColor: colors.black,
  },
  primaryText: {
    color: colors.white,
    fontFamily: fonts.semibold,
    fontSize: 17,
  },
  pressed: {
    opacity: 0.88,
    transform: [{ scale: 0.995 }],
  },
});
