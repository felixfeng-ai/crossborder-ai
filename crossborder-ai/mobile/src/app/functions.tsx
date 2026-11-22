import { router, type Href } from "expo-router";
import {
  Bell,
  Boxes,
  CalendarDays,
  ChevronRight,
  CircleAlert,
  ImagePlus,
  Images,
  MessageCircle,
  PackagePlus,
  RotateCcw,
  ShoppingBag,
  Star,
  Truck,
  UserRound,
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
import {
  useBootstrapQuery,
  useDailyPlanQuery,
  useNotificationsQuery,
  useTimelineQuery,
} from "@/api/queries";
import { IconWell } from "@/components/IconWell";
import { ModalScreenHeader } from "@/components/ModalScreenHeader";
import { colors, fonts, radii, type as typeScale } from "@/design/tokens";
import {
  buildFunctionHub,
  type FunctionShortcut,
} from "@/features/function-hub/catalog";
import { useAgentComposerStore } from "@/stores/agentComposer";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";

function ShortcutIcon({ id, size = 18 }: { id: string; size?: number }) {
  const common = { color: colors.inkSoft, size, strokeWidth: 1.7 };
  switch (id) {
    case "orders":
      return <ShoppingBag {...common} />;
    case "messages":
      return <MessageCircle {...common} />;
    case "pending-messages":
      return <MessageCircle {...common} />;
    case "review-replies":
      return <Star {...common} />;
    case "complaints":
      return <CircleAlert {...common} />;
    case "inventory":
      return <Boxes {...common} />;
    case "refund":
      return <RotateCcw {...common} />;
    case "listing":
      return <PackagePlus {...common} />;
    case "media":
      return <ImagePlus {...common} />;
    case "asset-library":
      return <Images {...common} />;
    case "plan":
      return <CalendarDays {...common} />;
    case "activity":
      return <Bell {...common} />;
    case "account":
      return <UserRound {...common} />;
    default:
      return <Truck {...common} />;
  }
}

export default function FunctionsScreen() {
  const token = useAuthStore((state) => state.token);
  const activeWorkspaceId = useWorkspaceStore(
    (state) => state.activeWorkspaceId,
  );
  const activeChannel = useWorkspaceStore((state) => state.activeChannel);
  const requestDraft = useAgentComposerStore((state) => state.requestDraft);
  const effectiveToken = PREVIEW_MODE ? "preview" : token;
  const bootstrap = useBootstrapQuery(effectiveToken);
  const workspaceId =
    activeWorkspaceId ?? bootstrap.data?.workspaces[0]?.id ?? null;
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
  const notifications = useNotificationsQuery(
    effectiveToken,
    workspaceId,
    activeChannel,
  );

  const loading =
    bootstrap.isLoading ||
    timeline.isLoading ||
    dailyPlan.isLoading ||
    notifications.isLoading;
  const hasError =
    timeline.isError || dailyPlan.isError || notifications.isError;
  const model = buildFunctionHub({
    items: timeline.data?.items ?? [],
    notifications: notifications.data ?? [],
    decisionCount: dailyPlan.data?.decision_count ?? 0,
  });

  const closeHub = () => {
    if (router.canGoBack()) {
      router.back();
      return;
    }
    router.replace("/");
  };

  const openShortcut = (shortcut: FunctionShortcut) => {
    const { target } = shortcut;
    if (target.type === "work-item") {
      router.push({
        pathname: "/task/[workItemId]",
        params: {
          workItemId: target.workItemId,
          workspaceId: workspaceId ?? "",
        },
      });
      return;
    }
    if (target.type === "route") {
      router.push(target.href as Href);
      return;
    }
    requestDraft(target.text);
    closeHub();
  };

  return (
    <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
      <ModalScreenHeader
        title="全部功能"
        variant="dismiss"
        accessibilityLabel="关闭全部功能"
        onBack={closeHub}
      />

      {loading ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.ink} />
        </View>
      ) : (
        <ScrollView
          style={styles.body}
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
        >
          {hasError && (
            <View style={styles.notice}>
              <Text style={styles.noticeTitle}>部分状态暂时无法同步</Text>
              <Text style={styles.noticeText}>
                仍可进入功能，数量会在恢复网络后更新。
              </Text>
            </View>
          )}

          <View style={styles.commonHeader}>
            <Text style={styles.sectionLabel}>常用</Text>
            <Text style={styles.commonMeta}>
              {model.common.length} 项快捷入口
            </Text>
          </View>
          <View style={styles.quickStrip}>
            {model.common.map((shortcut) => (
              <Pressable
                key={shortcut.id}
                accessibilityRole="button"
                accessibilityLabel={`${shortcut.title}${
                  shortcut.count > 0 ? `，${shortcut.count} 项待处理` : ""
                }`}
                onPress={() => openShortcut(shortcut)}
                style={({ pressed }) => [
                  styles.quickItem,
                  pressed && styles.quickItemPressed,
                ]}
              >
                <View>
                  <IconWell>
                    <ShortcutIcon id={shortcut.id} />
                  </IconWell>
                  {shortcut.count > 0 && <View style={styles.quickDot} />}
                </View>
                <Text style={styles.quickLabel} numberOfLines={1}>
                  {shortcut.title}
                </Text>
              </Pressable>
            ))}
          </View>

          {model.sections.map((section) => (
            <View key={section.id} style={styles.card}>
              <Text style={styles.cardLabel}>{section.title}</Text>
              <View>
                {section.shortcuts.map((shortcut, index) => (
                  <Pressable
                    key={shortcut.id}
                    accessibilityRole="button"
                    accessibilityLabel={shortcut.title}
                    onPress={() => openShortcut(shortcut)}
                    style={({ pressed }) => [
                      styles.row,
                      index > 0 && styles.rowDivider,
                      pressed && styles.rowPressed,
                    ]}
                  >
                    <IconWell>
                      <ShortcutIcon id={shortcut.id} size={17} />
                    </IconWell>
                    <View style={styles.rowCopy}>
                      <Text style={styles.rowTitle}>{shortcut.title}</Text>
                      <Text style={styles.rowDetail} numberOfLines={1}>
                        {shortcut.detail}
                      </Text>
                    </View>
                    {shortcut.count > 0 && (
                      <View style={styles.rowCount}>
                        <Text style={styles.rowCountText}>
                          {shortcut.count}
                        </Text>
                      </View>
                    )}
                    <ChevronRight
                      color={colors.faint}
                      size={16}
                      strokeWidth={2}
                    />
                  </Pressable>
                ))}
              </View>
            </View>
          ))}
        </ScrollView>
      )}
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
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.background,
  },
  content: {
    paddingHorizontal: 20,
    paddingTop: 4,
    paddingBottom: 44,
  },
  notice: {
    marginBottom: 14,
    padding: 14,
    borderRadius: radii.medium,
    backgroundColor: colors.amber,
  },
  noticeTitle: {
    color: colors.amberInk,
    fontFamily: fonts.semibold,
    fontSize: typeScale.meta,
    lineHeight: 18,
  },
  noticeText: {
    marginTop: 3,
    color: colors.amberInk,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 18,
    opacity: 0.8,
  },
  sectionLabel: {
    minHeight: 26,
    paddingTop: 6,
    color: colors.mutedStrong,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 18,
  },
  commonHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  commonMeta: {
    paddingTop: 6,
    color: colors.faint,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 18,
  },
  quickStrip: {
    flexDirection: "row",
    gap: 4,
  },
  quickItem: {
    minWidth: 0,
    minHeight: 82,
    flex: 1,
    paddingHorizontal: 2,
    paddingVertical: 10,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  quickItemPressed: {
    opacity: 0.55,
  },
  quickDot: {
    position: "absolute",
    top: -2,
    right: -3,
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: colors.amberDot,
  },
  quickLabel: {
    maxWidth: "100%",
    color: colors.inkSoft,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 17,
  },
  card: {
    marginTop: 18,
    paddingTop: 12,
    paddingBottom: 4,
    overflow: "hidden",
    borderRadius: radii.large,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    backgroundColor: colors.card,
  },
  cardLabel: {
    paddingHorizontal: 16,
    paddingBottom: 6,
    color: colors.mutedStrong,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 18,
  },
  row: {
    minHeight: 66,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  rowDivider: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
  },
  rowPressed: {
    opacity: 0.55,
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
    fontSize: typeScale.meta,
    lineHeight: 18,
  },
  rowCount: {
    width: 22,
    height: 22,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 11,
    backgroundColor: colors.amber,
  },
  rowCountText: {
    color: colors.amberInk,
    fontFamily: fonts.interSemibold,
    fontSize: typeScale.caption,
    lineHeight: 16,
    textAlign: "center",
  },
  pressed: {
    opacity: 0.72,
  },
});
