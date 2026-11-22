import { router } from "expo-router";
import { X } from "lucide-react-native";
import { Pressable, StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { PREVIEW_MODE } from "@/api/client";
import { useBootstrapQuery, useDailyPlanQuery, useTimelineQuery } from "@/api/queries";
import { ModalScreenHeader } from "@/components/ModalScreenHeader";
import { PlanAgenda } from "@/components/PlanAgenda";
import { colors } from "@/design/tokens";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";

export default function DailyPlanScreen() {
  const token = useAuthStore((state) => state.token);
  const activeWorkspaceId = useWorkspaceStore(
    (state) => state.activeWorkspaceId,
  );
  const activeChannel = useWorkspaceStore((state) => state.activeChannel);
  const effectiveToken = PREVIEW_MODE ? "preview" : token;
  const bootstrap = useBootstrapQuery(effectiveToken);
  const workspaceId =
    activeWorkspaceId ?? bootstrap.data?.workspaces[0]?.id ?? null;
  const plan = useDailyPlanQuery(
    effectiveToken,
    workspaceId,
    activeChannel,
  );
  // 计划接口不带时间字段，时间轴所需的 occurred_at / due_at 从同一天的 timeline 补齐。
  const timeline = useTimelineQuery(
    effectiveToken,
    workspaceId,
    activeChannel,
  );

  const openWorkItem = (workItemId: string) => {
    router.push({
      pathname: "/task/[workItemId]",
      params: {
        workItemId,
        workspaceId: workspaceId ?? "",
      },
    });
  };

  return (
    <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
      <ModalScreenHeader
        title="今日计划"
        onBack={() => router.back()}
        // 稿上左上返回、右上关闭：两个都在，关闭直接退出这一天的计划。
        right={
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="关闭今日计划"
            hitSlop={4}
            onPress={() => router.back()}
            style={({ pressed }) => [
              styles.closeButton,
              pressed && styles.pressed,
            ]}
          >
            <X color={colors.inkSoft} size={18} strokeWidth={1.9} />
          </Pressable>
        }
      />
      <PlanAgenda
        businessDate={plan.data?.business_date}
        decisionCount={plan.data?.decision_count ?? 0}
        autoCount={plan.data?.auto_count ?? 0}
        monitorCount={plan.data?.monitor_count ?? 0}
        items={plan.data?.items ?? []}
        timeline={timeline.data?.items ?? []}
        isLoading={plan.isLoading && !plan.data}
        hasError={plan.isError}
        onOpenWorkItem={openWorkItem}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.background,
  },
  closeButton: {
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 22,
  },
  pressed: {
    backgroundColor: colors.surface,
  },
});
