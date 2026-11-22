import { ChevronRight } from "lucide-react-native";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { TimelineItem } from "@/api/types";
import { TimeAxis } from "@/components/TimeAxis";
import { colors, fonts, radii, spacing } from "@/design/tokens";
import { commerceLabel } from "@/features/commerce/labels";
import { clockOf, deadlineText } from "@/features/time/relative";

type Props = {
  item: TimelineItem;
  onPress: () => void;
};

export function PrimaryTaskCard({ item, onPress }: Props) {
  const isUrgent = item.priority === "urgent";
  const requiresDecision = item.requires_action !== "none";
  const deadline = deadlineText(item.due_at);
  const startClock = clockOf(item.occurred_at);
  const commerce = commerceLabel(item.commerce);
  // 摘要自带句号，后面再接账目会出现「写好。 · 涉及」，先掐掉句尾。
  const summary = item.summary.replace(/[。.]\s*$/, "");
  const summaryLine = commerce ? `${summary} · ${commerce}` : item.summary;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${item.title}，${item.current_step}${
        deadline ? `，${deadline}` : ""
      }`}
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
    >
      <View style={styles.metaRow}>
        <Text style={styles.metaStrong}>
          {startClock ? `${startClock} · ` : ""}
          {isUrgent ? "订单异常" : "需要你决定"}
        </Text>
        <Text
          style={[
            styles.statusPill,
            !requiresDecision && styles.statusPillNeutral,
          ]}
        >
          {requiresDecision ? "待你决定" : "Agent 处理中"}
        </Text>
      </View>
      <Text style={styles.title}>{item.title}</Text>
      {/* 金额跟在摘要同一行：设计稿里账目是这句话的补充，不是新的一段。 */}
      <Text style={styles.summary}>{summaryLine}</Text>

      {item.due_at ? (
        <TimeAxis startAt={item.occurred_at} dueAt={item.due_at} tone="dark" />
      ) : null}

      <View style={styles.actionRow}>
        <View style={styles.action}>
          <Text style={styles.actionText}>
            {requiresDecision ? "处理这件事" : "查看进度"}
          </Text>
          <ChevronRight color={colors.ink} size={16} strokeWidth={2.2} />
        </View>
        <Text style={styles.actionState}>
          {requiresDecision
            ? (deadline ?? "方案已就绪")
            : "Agent 正在处理"}
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    marginTop: spacing.x2,
    padding: 16,
    borderRadius: radii.hero,
    backgroundColor: colors.black,
    shadowColor: colors.black,
    shadowOffset: { width: 0, height: 14 },
    shadowOpacity: 0.08,
    shadowRadius: 20,
    elevation: 5,
  },
  pressed: {
    transform: [{ scale: 0.995 }],
    opacity: 0.97,
  },
  metaRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.x3,
  },
  metaStrong: {
    color: "rgba(238, 242, 246, 0.68)",
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 17,
    fontVariant: ["tabular-nums"],
  },
  // 黑卡上唯一的彩色：琥珀语义色，深色字保证对比度。
  statusPill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    overflow: "hidden",
    borderRadius: radii.pill,
    backgroundColor: colors.amber,
    color: colors.amberInk,
    fontFamily: fonts.semibold,
    fontSize: 11,
    lineHeight: 15,
  },
  statusPillNeutral: {
    backgroundColor: "rgba(255, 255, 255, 0.1)",
    color: colors.faint,
  },
  title: {
    maxWidth: 292,
    marginTop: 12,
    color: colors.white,
    fontFamily: fonts.semibold,
    fontSize: 30,
    lineHeight: 36,
  },
  summary: {
    maxWidth: 322,
    marginTop: 8,
    color: "rgba(255, 255, 255, 0.62)",
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 18,
  },
  actionRow: {
    marginTop: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  action: {
    minHeight: 40,
    paddingHorizontal: 18,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    borderRadius: radii.pill,
    backgroundColor: colors.white,
  },
  actionText: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 14,
  },
  actionState: {
    color: "rgba(255, 255, 255, 0.55)",
    fontFamily: fonts.medium,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
  },
});
