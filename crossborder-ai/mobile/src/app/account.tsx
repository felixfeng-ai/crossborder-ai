import { router, type Href } from "expo-router";
import Constants from "expo-constants";
import {
  Building2,
  BellRing,
  Check,
  ChevronRight,
  LogOut,
  Power,
  Scale,
  ShieldCheck,
  Smartphone,
  Store,
  UserRound,
} from "lucide-react-native";
import { useState } from "react";
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { PREVIEW_MODE } from "@/api/client";
import {
  useAgentControlQuery,
  useBootstrapQuery,
  useSetAgentPausedMutation,
} from "@/api/queries";
import { AgentAvatar } from "@/components/AgentAvatar";
import { ModalScreenHeader } from "@/components/ModalScreenHeader";
import { colors, fonts, radii, type as typeScale } from "@/design/tokens";
import {
  workspaceRoleLabel,
  workspaceTypeLabel,
} from "@/features/account/account-labels";
import { LEGAL_CENTER_PATH } from "@/features/legal/documents";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";

function RowIcon({ children }: { children: React.ReactNode }) {
  return <View style={styles.rowIcon}>{children}</View>;
}

export default function AccountScreen() {
  const token = useAuthStore((state) => state.token);
  const logout = useAuthStore((state) => state.logout);
  const logoutAll = useAuthStore((state) => state.logoutAll);
  const activeWorkspaceId = useWorkspaceStore(
    (state) => state.activeWorkspaceId,
  );
  const clearWorkspace = useWorkspaceStore((state) => state.clear);
  const setActiveWorkspace = useWorkspaceStore(
    (state) => state.setActiveWorkspace,
  );
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [switchAccountOpen, setSwitchAccountOpen] = useState(false);
  const bootstrap = useBootstrapQuery(PREVIEW_MODE ? "preview" : token);
  const activeWorkspace =
    bootstrap.data?.workspaces.find(
      (workspace) => workspace.id === activeWorkspaceId,
    ) ?? bootstrap.data?.workspaces[0];
  const agentControl = useAgentControlQuery(
    PREVIEW_MODE ? "preview" : token,
    activeWorkspace?.id ?? null,
  );
  const setAgentPaused = useSetAgentPausedMutation(
    PREVIEW_MODE ? "preview" : token,
    activeWorkspace?.id ?? null,
  );
  const canControlAgent =
    activeWorkspace?.role === "owner" ||
    activeWorkspace?.role === "admin";

  const signOut = async () => {
    await logout();
    await clearWorkspace();
    router.replace("/sign-in");
  };
  const confirmSwitchAccount = () => {
    setSwitchAccountOpen(true);
  };
  const signOutAll = async () => {
    await logoutAll();
    await clearWorkspace();
    router.replace("/sign-in");
  };

  return (
    <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
      <ModalScreenHeader
        title="账号"
        variant="close"
        accessibilityLabel="关闭账号"
        onBack={() => router.back()}
      />

      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.card}>
          <View style={styles.profile}>
            <AgentAvatar size={44} />
            <View style={styles.profileCopy}>
              <Text style={styles.name}>{bootstrap.data?.display_name}</Text>
              <Text style={styles.workspace} numberOfLines={1}>
                {activeWorkspace?.name} ·{" "}
                {workspaceRoleLabel(activeWorkspace?.role)}
              </Text>
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="切换账号"
              onPress={confirmSwitchAccount}
              style={({ pressed }) => [
                styles.switchAccount,
                pressed && styles.pressed,
              ]}
            >
              <LogOut color={colors.mutedStrong} size={13} strokeWidth={1.8} />
              <Text style={styles.switchAccountText}>切换账号</Text>
            </Pressable>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardLabel}>工作区</Text>
          <View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="切换工作区"
              onPress={() => setWorkspaceOpen(true)}
              style={({ pressed }) => [
                styles.row,
                pressed && styles.pressed,
              ]}
            >
              <RowIcon>
                <Building2
                  color={colors.mutedStrong}
                  size={16}
                  strokeWidth={1.7}
                />
              </RowIcon>
              <Text style={styles.rowLabel}>当前工作区</Text>
              <Text style={styles.rowValue} numberOfLines={1}>
                {activeWorkspace?.name}
              </Text>
              <ChevronRight color={colors.faint} size={16} strokeWidth={2} />
            </Pressable>
            <View style={[styles.row, styles.rowDivided]}>
              <RowIcon>
                <UserRound
                  color={colors.mutedStrong}
                  size={16}
                  strokeWidth={1.7}
                />
              </RowIcon>
              <Text style={styles.rowLabel}>我的角色</Text>
              <Text style={styles.rowValue}>
                {workspaceRoleLabel(activeWorkspace?.role)}
              </Text>
            </View>
            <View style={[styles.row, styles.rowDivided]}>
              <RowIcon>
                <ShieldCheck
                  color={colors.mutedStrong}
                  size={16}
                  strokeWidth={1.7}
                />
              </RowIcon>
              <Text style={styles.rowLabel}>工作区类型</Text>
              <Text style={styles.rowValue}>
                {workspaceTypeLabel(activeWorkspace?.type)}
              </Text>
            </View>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardLabel}>店铺</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="打开店铺与渠道"
            onPress={() => router.push("/stores" as Href)}
            style={({ pressed }) => [
              styles.row,
              pressed && styles.pressed,
            ]}
          >
            <RowIcon>
              <Store
                color={colors.mutedStrong}
                size={16}
                strokeWidth={1.7}
              />
            </RowIcon>
            <Text style={styles.rowLabel}>店铺与渠道</Text>
            <Text style={styles.rowValue}>连接与查看店铺</Text>
            <ChevronRight color={colors.faint} size={16} strokeWidth={2} />
          </Pressable>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardLabel}>Agent 值班</Text>
          <View style={styles.agentRow}>
            <RowIcon>
              <Power color={colors.mutedStrong} size={16} strokeWidth={1.7} />
            </RowIcon>
            <View style={styles.agentCopy}>
              <Text style={styles.rowLabel}>
                {agentControl.data?.paused ? "小 Veya 已暂停" : "小 Veya 在线值守"}
              </Text>
              <Text style={styles.agentStatus}>
                {agentControl.data?.paused
                  ? "暂停后不再自动处理任务"
                  : "每天 09:00–20:00 自动处理"}
              </Text>
            </View>
            <Pressable
              accessibilityRole="switch"
              accessibilityLabel="切换 Agent 值班"
              accessibilityState={{
                checked: !agentControl.data?.paused,
                disabled: !canControlAgent || setAgentPaused.isPending,
              }}
              aria-checked={!agentControl.data?.paused}
              disabled={!canControlAgent || setAgentPaused.isPending}
              onPress={() =>
                setAgentPaused.mutate(!Boolean(agentControl.data?.paused))
              }
              style={({ pressed }) => [
                styles.agentSwitch,
                !agentControl.data?.paused && styles.agentSwitchOn,
                (!canControlAgent || setAgentPaused.isPending) &&
                  styles.agentSwitchDisabled,
                pressed && styles.pressed,
              ]}
            >
              <View
                style={[
                  styles.agentSwitchThumb,
                  !agentControl.data?.paused && styles.agentSwitchThumbOn,
                ]}
              />
            </Pressable>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardLabel}>提醒</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="打开通知偏好"
            onPress={() =>
              router.push("/notification-settings" as Href)
            }
            style={({ pressed }) => [
              styles.row,
              pressed && styles.pressed,
            ]}
          >
            <RowIcon>
              <BellRing
                color={colors.mutedStrong}
                size={16}
                strokeWidth={1.7}
              />
            </RowIcon>
            <Text style={styles.rowLabel}>通知偏好</Text>
            <Text style={styles.rowValue}>提醒与免打扰</Text>
            <ChevronRight color={colors.faint} size={16} strokeWidth={2} />
          </Pressable>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardLabel}>法律与隐私</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="打开法律与隐私"
            onPress={() => router.push(LEGAL_CENTER_PATH as Href)}
            style={({ pressed }) => [
              styles.row,
              pressed && styles.pressed,
            ]}
          >
            <RowIcon>
              <Scale
                color={colors.mutedStrong}
                size={16}
                strokeWidth={1.7}
              />
            </RowIcon>
            <Text style={styles.rowLabel}>法律与隐私</Text>
            <Text style={styles.rowValue}>协议、AI 与数据</Text>
            <ChevronRight color={colors.faint} size={16} strokeWidth={2} />
          </Pressable>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardLabel}>安全设置</Text>
          <View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="退出全部设备"
              onPress={signOutAll}
              style={({ pressed }) => [
                styles.row,
                pressed && styles.pressed,
              ]}
            >
              <RowIcon>
                <Smartphone
                  color={colors.mutedStrong}
                  size={16}
                  strokeWidth={1.7}
                />
              </RowIcon>
              <Text style={styles.rowLabel}>退出全部设备</Text>
              <ChevronRight color={colors.faint} size={16} strokeWidth={2} />
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="退出当前设备"
              onPress={signOut}
              style={({ pressed }) => [
                styles.row,
                styles.rowDivided,
                pressed && styles.pressed,
              ]}
            >
              <RowIcon>
                <LogOut color={colors.danger} size={16} strokeWidth={1.7} />
              </RowIcon>
              <Text style={[styles.rowLabel, styles.dangerText]}>
                退出登录
              </Text>
            </Pressable>
          </View>
        </View>

        <Text style={styles.version}>
          VeyaShip {Constants.expoConfig?.version ?? "1.0.0"} · 预览版
        </Text>
      </ScrollView>

      <Modal
        transparent
        visible={workspaceOpen}
        animationType="slide"
        onRequestClose={() => setWorkspaceOpen(false)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setWorkspaceOpen(false)}
        />
        <SafeAreaView style={styles.sheet} edges={["bottom"]}>
          <View style={styles.sheetHandle} />
          <Text style={styles.sheetTitle}>切换工作区</Text>
          <Text style={styles.sheetText}>
            切换后，首页、计划、通知和任务会使用新工作区。
          </Text>
          <View style={styles.workspaceList}>
            {bootstrap.data?.workspaces.map((workspace) => {
              const selected = workspace.id === activeWorkspace?.id;
              return (
                <Pressable
                  key={workspace.id}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  accessibilityLabel={`切换到 ${workspace.name}`}
                  onPress={() => {
                    void setActiveWorkspace(workspace);
                    setWorkspaceOpen(false);
                  }}
                  style={({ pressed }) => [
                    styles.workspaceOption,
                    selected && styles.workspaceOptionSelected,
                    pressed && styles.pressed,
                  ]}
                >
                  <View style={styles.workspaceOptionCopy}>
                    <Text style={styles.workspaceOptionName}>
                      {workspace.name}
                    </Text>
                    <Text style={styles.workspaceOptionMeta}>
                      {workspaceRoleLabel(workspace.role)} ·{" "}
                      {workspaceTypeLabel(workspace.type)}
                    </Text>
                  </View>
                  {selected && (
                    <View style={styles.workspaceCheck}>
                      <Check
                        color={colors.white}
                        size={12}
                        strokeWidth={2.2}
                      />
                    </View>
                  )}
                </Pressable>
              );
            })}
          </View>
        </SafeAreaView>
      </Modal>

      <Modal
        transparent
        visible={switchAccountOpen}
        animationType="slide"
        onRequestClose={() => setSwitchAccountOpen(false)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setSwitchAccountOpen(false)}
        />
        <SafeAreaView style={styles.sheet} edges={["bottom"]}>
          <View style={styles.sheetHandle} />
          <Text style={styles.sheetTitle}>切换账号</Text>
          <Text style={styles.sheetText}>
            将退出当前账号并返回登录页，工作区数据不会删除。
          </Text>
          <View style={styles.sheetActions}>
            <Pressable
              accessibilityRole="button"
              onPress={() => setSwitchAccountOpen(false)}
              style={({ pressed }) => [
                styles.sheetButton,
                styles.sheetButtonSecondary,
                pressed && styles.pressed,
              ]}
            >
              <Text style={styles.sheetButtonSecondaryText}>取消</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              onPress={() => {
                setSwitchAccountOpen(false);
                void signOut();
              }}
              style={({ pressed }) => [
                styles.sheetButton,
                styles.sheetButtonDanger,
                pressed && styles.pressed,
              ]}
            >
              <Text style={styles.sheetButtonDangerText}>切换账号</Text>
            </Pressable>
          </View>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    flexGrow: 1,
    paddingHorizontal: 20,
    paddingTop: 4,
    paddingBottom: 40,
    backgroundColor: colors.background,
  },
  card: {
    marginTop: 16,
    paddingTop: 12,
    paddingBottom: 4,
    overflow: "hidden",
    borderRadius: radii.large,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    backgroundColor: colors.card,
  },
  profile: {
    paddingHorizontal: 16,
    paddingBottom: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  profileCopy: {
    flex: 1,
    minWidth: 0,
    gap: 4,
  },
  switchAccount: {
    minHeight: 44,
    paddingHorizontal: 10,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 5,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    borderRadius: radii.pill,
    backgroundColor: colors.surface,
  },
  switchAccountText: {
    color: colors.mutedStrong,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 18,
  },
  name: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: typeScale.pageTitle,
    lineHeight: 28,
  },
  workspace: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 18,
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
    minHeight: 58,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  rowDivided: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
  },
  // 与首页列表行同一个底座：34 圆、发丝描边、白底、不填色。
  rowIcon: {
    width: 34,
    height: 34,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 17,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    backgroundColor: colors.card,
  },
  rowLabel: {
    flex: 1,
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: typeScale.body,
    lineHeight: 21,
  },
  rowValue: {
    maxWidth: "44%",
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 18,
  },
  agentRow: {
    minHeight: 66,
    paddingHorizontal: 16,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  agentCopy: {
    flex: 1,
    gap: 2,
  },
  agentStatus: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 17,
  },
  agentSwitch: {
    width: 42,
    height: 24,
    padding: 2,
    justifyContent: "center",
    borderRadius: 12,
    backgroundColor: colors.cardBorder,
  },
  agentSwitchOn: {
    backgroundColor: colors.ink,
  },
  agentSwitchDisabled: {
    opacity: 0.42,
  },
  agentSwitchThumb: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.white,
  },
  agentSwitchThumbOn: {
    transform: [{ translateX: 18 }],
  },
  pressed: {
    opacity: 0.55,
  },
  dangerText: {
    color: colors.danger,
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
    backgroundColor: colors.cardBorder,
  },
  sheetTitle: {
    marginTop: 22,
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: typeScale.pageTitle,
    lineHeight: 30,
  },
  sheetText: {
    marginTop: 8,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 20,
  },
  sheetActions: {
    marginTop: 22,
    marginBottom: 10,
    flexDirection: "row",
    gap: 10,
  },
  sheetButton: {
    minHeight: 52,
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radii.small,
  },
  sheetButtonSecondary: {
    backgroundColor: colors.surfaceQuiet,
  },
  sheetButtonSecondaryText: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: typeScale.body,
  },
  sheetButtonDanger: {
    backgroundColor: colors.danger,
  },
  sheetButtonDangerText: {
    color: colors.white,
    fontFamily: fonts.semibold,
    fontSize: typeScale.body,
  },
  workspaceList: {
    marginTop: 16,
    gap: 8,
  },
  workspaceOption: {
    minHeight: 64,
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
  workspaceOptionSelected: {
    borderColor: colors.ink,
  },
  workspaceOptionCopy: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
  workspaceOptionName: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: typeScale.body,
    lineHeight: 20,
  },
  workspaceOptionMeta: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 17,
  },
  workspaceCheck: {
    width: 22,
    height: 22,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 11,
    backgroundColor: colors.ink,
  },
  version: {
    marginTop: 24,
    color: colors.faint,
    fontFamily: fonts.inter,
    fontSize: typeScale.caption,
    lineHeight: 18,
    textAlign: "center",
  },
});
