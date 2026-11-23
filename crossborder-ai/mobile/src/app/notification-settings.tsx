import { router } from "expo-router";
import { BellRing, Moon, Save, TimerReset } from "lucide-react-native";
import { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { PREVIEW_MODE } from "@/api/client";
import {
  useBootstrapQuery,
  useNotificationPreferencesQuery,
  useUpdateNotificationPreferencesMutation,
} from "@/api/queries";
import type { NotificationPreferences } from "@/api/types";
import { ModalScreenHeader } from "@/components/ModalScreenHeader";
import { QueryErrorState } from "@/components/QueryErrorState";
import { colors, fonts, radii, type as typeScale } from "@/design/tokens";
import {
  canEditNotificationPreferences,
  formatHour,
  validatePreferenceDraft,
} from "@/features/notifications/preference-form";
import { resolveQueryState } from "@/features/query-state/query-state";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";

type BooleanPreferenceKey =
  | "morning_brief"
  | "day_closeout"
  | "needs_action"
  | "action_failed"
  | "authorization_expired";

const booleanRows: {
  key: BooleanPreferenceKey;
  title: string;
  detail: string;
}[] = [
  {
    key: "morning_brief",
    title: "晨间计划",
    detail: "每天开始工作时收到今日安排",
  },
  {
    key: "day_closeout",
    title: "每日日结",
    detail: "Agent 完成一天工作后发送结果",
  },
  {
    key: "needs_action",
    title: "等待你决定",
    detail: "有高风险动作或结果需要确认",
  },
  {
    key: "action_failed",
    title: "执行失败",
    detail: "动作失败或平台回读不一致",
  },
  {
    key: "authorization_expired",
    title: "授权失效",
    detail: "店铺连接过期或权限不足",
  },
];

function hourValue(value: number | null, direction: -1 | 1) {
  if (value == null) return direction > 0 ? 22 : null;
  return (value + direction + 24) % 24;
}

export default function NotificationSettingsScreen() {
  const token = useAuthStore((state) => state.token);
  const activeWorkspaceId = useWorkspaceStore(
    (state) => state.activeWorkspaceId,
  );
  const effectiveToken = PREVIEW_MODE ? "preview" : token;
  const bootstrap = useBootstrapQuery(effectiveToken);
  const workspace =
    bootstrap.data?.workspaces.find(
      (item) => item.id === activeWorkspaceId,
    ) ?? bootstrap.data?.workspaces[0];
  const workspaceId = workspace?.id ?? null;
  const preferences = useNotificationPreferencesQuery(
    effectiveToken,
    workspaceId,
  );
  const update = useUpdateNotificationPreferencesMutation(
    effectiveToken,
    workspaceId,
  );
  const [draftState, setDraftState] = useState<{
    workspaceId: string | null;
    changes: Partial<NotificationPreferences>;
  }>({ workspaceId: null, changes: {} });
  const [error, setError] = useState("");
  const editable = canEditNotificationPreferences(workspace?.role);
  const queryState = resolveQueryState({
    isLoading: preferences.isLoading,
    isError: preferences.isError,
    hasData: Boolean(preferences.data),
  });

  const changes =
    draftState.workspaceId === workspaceId ? draftState.changes : {};
  const draft = preferences.data
    ? { ...preferences.data, ...changes }
    : null;

  const updateDraft = (changesToApply: Partial<NotificationPreferences>) => {
    setDraftState({
      workspaceId,
      changes: { ...changes, ...changesToApply },
    });
  };

  const setFlag = (key: BooleanPreferenceKey, value: boolean) => {
    if (!editable) return;
    updateDraft({ [key]: value });
  };

  const save = async () => {
    if (!draft || !editable || update.isPending) return;
    const validation = validatePreferenceDraft({
      timezone: draft.timezone,
      quietStartHour: draft.quiet_start_hour,
      quietEndHour: draft.quiet_end_hour,
    });
    if (validation) {
      setError(validation);
      return;
    }
    setError("");
    try {
      const saved = await update.mutateAsync(draft);
      updateDraft(saved);
      setDraftState({ workspaceId, changes: {} });
      Alert.alert("已保存", "新的通知偏好会从下一条通知开始生效。");
    } catch {
      setDraftState({ workspaceId, changes: {} });
      Alert.alert("没有保存", "通知偏好已恢复，请稍后重试。");
    }
  };

  if (queryState === "loading") {
    return (
      <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
        <ModalScreenHeader
          title="通知偏好"
          onBack={() => router.back()}
        />
        <View style={styles.loading}>
          <ActivityIndicator color={colors.ink} />
        </View>
      </SafeAreaView>
    );
  }
  if (queryState === "error" || !draft) {
    return (
      <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
        <ModalScreenHeader
          title="通知偏好"
          onBack={() => router.back()}
        />
        <QueryErrorState
          error={preferences.error}
          title="通知偏好暂时无法同步"
          onRetry={() => void preferences.refetch()}
        />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView
      style={styles.safe}
      edges={["left", "right", "bottom"]}
    >
      <ModalScreenHeader
        title="通知偏好"
        onBack={() => router.back()}
      />
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {!editable && (
          <View style={styles.readOnly}>
            <Text style={styles.readOnlyText}>
              当前角色只能查看通知偏好，不能修改。
            </Text>
          </View>
        )}

        <View style={styles.card}>
          <View style={styles.cardTitleRow}>
            <BellRing color={colors.mutedStrong} size={17} strokeWidth={1.7} />
            <Text style={styles.cardTitle}>提醒类型</Text>
          </View>
          {booleanRows.map((row, index) => (
            <View
              key={row.key}
              style={[styles.row, index > 0 && styles.rowDivided]}
            >
              <View style={styles.rowCopy}>
                <Text style={styles.rowTitle}>{row.title}</Text>
                <Text style={styles.rowDetail}>{row.detail}</Text>
              </View>
              <Switch
                accessibilityLabel={row.title}
                disabled={!editable}
                onValueChange={(value) => setFlag(row.key, value)}
                value={draft[row.key]}
              />
            </View>
          ))}
        </View>

        <View style={styles.card}>
          <View style={styles.cardTitleRow}>
            <Moon color={colors.mutedStrong} size={17} strokeWidth={1.7} />
            <Text style={styles.cardTitle}>免打扰</Text>
          </View>
          <View style={styles.row}>
            <View style={styles.rowCopy}>
              <Text style={styles.rowTitle}>免打扰时段</Text>
              <Text style={styles.rowDetail}>
                高优先级失败和授权失效不受安静时段影响
              </Text>
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="关闭免打扰"
              disabled={!editable}
              onPress={() => {
                updateDraft({
                  quiet_start_hour: null,
                  quiet_end_hour: null,
                });
              }}
            >
              <Text style={styles.clearAction}>关闭</Text>
            </Pressable>
          </View>
          <View style={[styles.row, styles.rowDivided]}>
            <Text style={styles.hourLabel}>开始</Text>
            <HourStepper
              disabled={!editable}
              value={draft.quiet_start_hour}
              onChange={(value) =>
                updateDraft({ quiet_start_hour: value })
              }
            />
            <Text style={styles.hourLabel}>结束</Text>
            <HourStepper
              disabled={!editable}
              value={draft.quiet_end_hour}
              onChange={(value) =>
                updateDraft({ quiet_end_hour: value })
              }
            />
          </View>
        </View>

        <View style={styles.card}>
          <View style={styles.cardTitleRow}>
            <TimerReset color={colors.mutedStrong} size={17} strokeWidth={1.7} />
            <Text style={styles.cardTitle}>时区</Text>
          </View>
          <View style={styles.timezoneBody}>
            <TextInput
              accessibilityLabel="通知时区"
              autoCapitalize="none"
              autoCorrect={false}
              editable={editable}
              onChangeText={(value) => {
                updateDraft({ timezone: value });
                if (error) setError("");
              }}
              placeholder="Asia/Shanghai"
              placeholderTextColor={colors.faint}
              style={[styles.timezoneInput, !editable && styles.inputDisabled]}
              value={draft.timezone}
            />
            <Text style={styles.rowDetail}>
              使用 IANA 时区名称，例如 Asia/Shanghai。
            </Text>
            {!!error && <Text style={styles.errorText}>{error}</Text>}
          </View>
        </View>
      </ScrollView>

      {editable && (
        <View style={styles.footer}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="保存通知偏好"
            disabled={update.isPending}
            onPress={() => void save()}
            style={({ pressed }) => [
              styles.primary,
              pressed && styles.pressed,
            ]}
          >
            {update.isPending ? (
              <ActivityIndicator color={colors.white} size="small" />
            ) : (
              <>
                <Save color={colors.white} size={16} strokeWidth={1.9} />
                <Text style={styles.primaryText}>保存通知偏好</Text>
              </>
            )}
          </Pressable>
        </View>
      )}
    </SafeAreaView>
  );
}

function HourStepper({
  value,
  onChange,
  disabled,
}: {
  value: number | null;
  onChange: (value: number | null) => void;
  disabled: boolean;
}) {
  return (
    <View style={[styles.stepper, disabled && styles.stepperDisabled]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="提前一小时"
        disabled={disabled}
        onPress={() => onChange(hourValue(value, -1))}
        style={styles.stepButton}
      >
        <Text style={styles.stepButtonText}>−</Text>
      </Pressable>
      <Text style={styles.stepValue}>{formatHour(value)}</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="延后一小时"
        disabled={disabled}
        onPress={() => onChange(hourValue(value, 1))}
        style={styles.stepButton}
      >
        <Text style={styles.stepButtonText}>＋</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.background,
  },
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  content: {
    paddingHorizontal: 20,
    paddingTop: 6,
    paddingBottom: 100,
  },
  readOnly: {
    marginBottom: 12,
    padding: 14,
    borderRadius: radii.medium,
    backgroundColor: colors.surface,
  },
  readOnlyText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 20,
  },
  card: {
    marginTop: 14,
    paddingTop: 12,
    overflow: "hidden",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    borderRadius: radii.large,
    backgroundColor: colors.card,
  },
  cardTitleRow: {
    minHeight: 30,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  cardTitle: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: typeScale.body,
    lineHeight: 21,
  },
  row: {
    minHeight: 62,
    paddingHorizontal: 16,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  rowDivided: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
  },
  rowCopy: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
  rowTitle: {
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: typeScale.body,
    lineHeight: 21,
  },
  rowDetail: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 17,
  },
  clearAction: {
    color: colors.mutedStrong,
    fontFamily: fonts.semibold,
    fontSize: typeScale.meta,
  },
  hourLabel: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
  },
  stepper: {
    flex: 1,
    minHeight: 38,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderRadius: 10,
    backgroundColor: colors.surface,
  },
  stepperDisabled: {
    opacity: 0.5,
  },
  stepButton: {
    width: 38,
    height: 38,
    alignItems: "center",
    justifyContent: "center",
  },
  stepButtonText: {
    color: colors.ink,
    fontFamily: fonts.interSemibold,
    fontSize: 18,
  },
  stepValue: {
    color: colors.ink,
    fontFamily: fonts.inter,
    fontSize: typeScale.meta,
    fontVariant: ["tabular-nums"],
  },
  timezoneBody: {
    paddingHorizontal: 16,
    paddingBottom: 16,
    gap: 8,
  },
  timezoneInput: {
    minHeight: 46,
    paddingHorizontal: 13,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: radii.small,
    color: colors.ink,
    fontFamily: fonts.inter,
    fontSize: typeScale.body,
    backgroundColor: colors.card,
  },
  inputDisabled: {
    color: colors.muted,
    backgroundColor: colors.surface,
  },
  errorText: {
    color: colors.danger,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 17,
  },
  footer: {
    position: "absolute",
    right: 18,
    bottom: 18,
    left: 18,
  },
  primary: {
    minHeight: 52,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    borderRadius: radii.pill,
    backgroundColor: colors.ink,
  },
  primaryText: {
    color: colors.white,
    fontFamily: fonts.semibold,
    fontSize: typeScale.body,
  },
  pressed: {
    opacity: 0.7,
  },
});
