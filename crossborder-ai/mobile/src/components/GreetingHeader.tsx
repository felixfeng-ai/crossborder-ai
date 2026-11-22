import { BellRing } from "lucide-react-native";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { AgentAvatar } from "@/components/AgentAvatar";
import { colors, fonts } from "@/design/tokens";

type Props = {
  displayName: string;
  agentState?: string;
  onOpenNotifications: () => void;
};

export function GreetingHeader({
  displayName,
  agentState = "小 Veya 在线",
  onOpenNotifications,
}: Props) {
  return (
    <View style={styles.row}>
      <AgentAvatar />
      <View style={styles.copy}>
        <Text style={styles.title} numberOfLines={1}>
          早上好，{displayName}
        </Text>
        <View style={styles.statusRow}>
          {/* 绿点只表示「Agent 在线」，不是装饰；离线时应换成灰色并同步文案。 */}
          <View style={styles.onlineDot} />
          <Text style={styles.status} numberOfLines={1}>
            {agentState}
          </Text>
        </View>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="查看通知"
        hitSlop={4}
        onPress={onOpenNotifications}
        style={({ pressed }) => [styles.bell, pressed && styles.pressed]}
      >
        <BellRing color={colors.ink} size={19} strokeWidth={1.8} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    minHeight: 52,
  },
  copy: {
    flex: 1,
    minWidth: 0,
  },
  title: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 18,
    lineHeight: 24,
  },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    marginTop: 3,
  },
  onlineDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: colors.green,
  },
  status: {
    flex: 1,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 17,
  },
  // 通知按钮是实心浅灰圆，不加描边：描边会和卡片发丝线混在一起。
  bell: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.graySoft,
  },
  pressed: {
    opacity: 0.72,
    transform: [{ scale: 0.97 }],
  },
});
