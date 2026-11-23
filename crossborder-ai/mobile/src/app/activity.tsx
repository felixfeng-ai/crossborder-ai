import { router } from "expo-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  CalendarDays,
  MessageCircle,
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

import {
  PREVIEW_MODE,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/api/client";
import { useBootstrapQuery, useNotificationsQuery } from "@/api/queries";
import type { NotificationItem } from "@/api/types";
import { IconWell } from "@/components/IconWell";
import { ModalScreenHeader } from "@/components/ModalScreenHeader";
import { PageLoader } from "@/components/PageLoader";
import { QueryErrorState } from "@/components/QueryErrorState";
import { colors, fonts, radii, type as typeScale } from "@/design/tokens";
import { groupNotificationsByDay } from "@/features/activity/notification-groups";
import { resolveQueryState } from "@/features/query-state/query-state";
import { navigateDeepLink } from "@/notifications/deepLink";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";

function NotificationIcon({ type }: { type: string }) {
  const iconProps = {
    color: colors.mutedStrong,
    size: 16,
    strokeWidth: 1.7,
  };
  if (type === "morning_brief" || type === "day_closeout") {
    return <CalendarDays {...iconProps} />;
  }
  if (type === "action_failed") {
    return <TriangleAlert {...iconProps} />;
  }
  if (type === "needs_action") return <MessageCircle {...iconProps} />;
  return <Bell {...iconProps} />;
}

export default function ActivityScreen() {
  const token = useAuthStore((state) => state.token);
  const activeWorkspaceId = useWorkspaceStore(
    (state) => state.activeWorkspaceId,
  );
  const activeChannel = useWorkspaceStore((state) => state.activeChannel);
  const effectiveToken = PREVIEW_MODE ? "preview" : token;
  const bootstrap = useBootstrapQuery(effectiveToken);
  const workspaceId =
    activeWorkspaceId ?? bootstrap.data?.workspaces[0]?.id ?? null;
  const notifications = useNotificationsQuery(
    effectiveToken,
    workspaceId,
    activeChannel,
  );
  const queryClient = useQueryClient();
  const items = notifications.data ?? [];
  const groups = groupNotificationsByDay(items);
  const unreadCount = items.filter((item) => !item.read_at).length;
  const queryKey = [
    "mobile",
    "notifications",
    workspaceId,
    activeChannel?.channelType,
    activeChannel?.channelId,
  ];
  const queryState = resolveQueryState({
    isLoading: notifications.isLoading,
    isError: notifications.isError,
    hasData: Boolean(notifications.data),
  });

  const markRead = useMutation({
    mutationFn: async () => {
      // 先本地置已读，失败时再拉回真实状态，避免按钮点下没反馈。
      queryClient.setQueryData<NotificationItem[]>(queryKey, (previous) =>
        previous?.map((item) =>
          item.read_at
            ? item
            : { ...item, read_at: new Date().toISOString() },
        ),
      );
      if (PREVIEW_MODE) return { marked: unreadCount };
      return markAllNotificationsRead(effectiveToken!, workspaceId!);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey });
    },
    onError: async () => {
      await queryClient.invalidateQueries({ queryKey });
    },
  });
  const markOneRead = useMutation({
    mutationFn: async (notificationId: string) => {
      queryClient.setQueryData<NotificationItem[]>(queryKey, (previous) =>
        previous?.map((item) =>
          item.id === notificationId && !item.read_at
            ? { ...item, read_at: new Date().toISOString() }
            : item,
        ),
      );
      if (PREVIEW_MODE) return { id: notificationId };
      return markNotificationRead(
        effectiveToken!,
        workspaceId!,
        notificationId,
      );
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey });
    },
  });

  // 首屏还没回来时走加载态，别先弹「暂无通知」再跳成列表。
  if (queryState === "loading") {
    return <PageLoader />;
  }
  if (queryState === "error") {
    return (
      <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
        <ModalScreenHeader
          title="通知"
          variant="back"
          accessibilityLabel="返回"
          onBack={() => router.back()}
        />
        <QueryErrorState
          error={notifications.error}
          title="通知暂时无法同步"
          description="当前不会把请求失败显示成暂无通知。"
          onRetry={() => void notifications.refetch()}
        />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
      <ModalScreenHeader
        title="通知"
        variant="back"
        accessibilityLabel="返回"
        onBack={() => router.back()}
        right={
          unreadCount > 0 ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="全部已读"
              disabled={markRead.isPending}
              hitSlop={6}
              onPress={() => markRead.mutate()}
              style={({ pressed }) => [
                styles.markAll,
                pressed && styles.markAllPressed,
              ]}
            >
              {markRead.isPending ? (
                <ActivityIndicator color={colors.muted} size="small" />
              ) : (
                <Text style={styles.markAllText}>全部已读</Text>
              )}
            </Pressable>
          ) : null
        }
      />
      <ScrollView
        style={styles.body}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {items.length === 0 ? (
          <View style={styles.empty}>
            <View style={styles.emptyIcon}>
              <Bell color={colors.muted} size={22} strokeWidth={1.6} />
            </View>
            <Text style={styles.emptyTitle}>暂无通知</Text>
            <Text style={styles.emptyText}>
              需要你决定、失败或等待外部响应时，会出现在这里。
            </Text>
          </View>
        ) : (
          <>
            {groups.map((group) => (
              <View key={group.key} style={styles.section}>
                <Text style={styles.sectionTitle}>{group.title}</Text>
                <View style={styles.card}>
                  {group.items.map((item, index) => (
                    <Pressable
                      key={item.id}
                      accessibilityRole="button"
                      accessibilityLabel={`${item.title}，${item.typeLabel}`}
                      onPress={() => {
                        const navigation = () =>
                          navigateDeepLink(item.deep_link);
                        if (item.read_at) {
                          navigation();
                          return;
                        }
                        // 点击即视为已读，网络失败后由 onSettled 拉回真实状态。
                        void markOneRead
                          .mutateAsync(item.id)
                          .finally(navigation);
                      }}
                      style={({ pressed }) => [
                        styles.row,
                        index > 0 && styles.rowDivided,
                        pressed && styles.pressed,
                      ]}
                    >
                      <IconWell>
                        <NotificationIcon type={item.notification_type} />
                      </IconWell>
                      <View style={styles.rowCopy}>
                        <View style={styles.rowHead}>
                          <Text
                            numberOfLines={1}
                            style={[
                              styles.rowTitle,
                              item.unread && styles.rowTitleUnread,
                            ]}
                          >
                            {item.title}
                          </Text>
                          {item.unread ? (
                            <View
                              accessibilityLabel="未读"
                              style={styles.unreadDot}
                            />
                          ) : (
                            <Text style={styles.rowTime}>{item.timeLabel}</Text>
                          )}
                        </View>
                        <Text numberOfLines={2} style={styles.rowText}>
                          {item.body}
                        </Text>
                      </View>
                    </Pressable>
                  ))}
                </View>
              </View>
            ))}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  // 导航层白、内容层灰：与设计稿一致的两层结构，header 与状态栏连成一块白面。
  safe: {
    flex: 1,
    backgroundColor: colors.background,
  },
  body: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 48,
  },
  empty: {
    paddingTop: 110,
    alignItems: "center",
    paddingHorizontal: 24,
  },
  emptyIcon: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
  },
  emptyTitle: {
    marginTop: 20,
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: typeScale.body,
    lineHeight: 24,
  },
  emptyText: {
    maxWidth: 280,
    marginTop: 8,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 20,
    textAlign: "center",
  },
  section: {
    marginTop: 20,
  },
  sectionTitle: {
    marginBottom: 8,
    paddingLeft: 4,
    color: colors.mutedStrong,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 18,
  },
  card: {
    overflow: "hidden",
    borderRadius: radii.large,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    backgroundColor: colors.card,
  },
  row: {
    minHeight: 68,
    paddingVertical: 12,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 12,
  },
  rowDivided: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
  },
  pressed: {
    opacity: 0.55,
  },
  markAll: {
    minHeight: 32,
    paddingHorizontal: 6,
    alignItems: "center",
    justifyContent: "center",
  },
  markAllPressed: {
    opacity: 0.55,
  },
  markAllText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 18,
  },
  unreadDot: {
    width: 8,
    height: 8,
    marginTop: 6,
    borderRadius: 4,
    backgroundColor: colors.unread,
  },
  rowCopy: {
    flex: 1,
    minWidth: 0,
    gap: 4,
  },
  rowHead: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 8,
  },
  rowTitle: {
    flex: 1,
    minWidth: 0,
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: typeScale.body,
    lineHeight: 21,
  },
  rowTitleUnread: {
    fontFamily: fonts.semibold,
  },
  rowText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 19,
  },
  rowTime: {
    color: colors.faint,
    fontFamily: fonts.inter,
    fontSize: typeScale.caption,
    lineHeight: 18,
    fontVariant: ["tabular-nums"],
  },
});
