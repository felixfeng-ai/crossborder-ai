import {
  Box,
  CalendarDays,
  ChevronRight,
  CircleAlert,
  Clock3,
  MessageSquareText,
} from "lucide-react-native";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import type { DailyPlanItem, TimelineItem } from "@/api/types";
import { TimeAxis } from "@/components/TimeAxis";
import { colors, fonts, radii } from "@/design/tokens";
import { commerceLabel } from "@/features/commerce/labels";
import { deadlineText, untilHour } from "@/features/time/relative";

type Props = {
  businessDate?: string;
  decisionCount: number;
  autoCount: number;
  monitorCount: number;
  items: DailyPlanItem[];
  /** 用来补时间轴需要的 occurred_at / due_at：计划接口本身不带时间。 */
  timeline?: TimelineItem[];
  isLoading: boolean;
  hasError: boolean;
  onOpenWorkItem: (workItemId: string) => void;
};

function formatBusinessDate(value?: string) {
  if (!value) return "今天";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return value;
  const date = new Date(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
  );
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  return `${Number(match[2])}月${Number(match[3])}日 · ${
    weekdays[date.getDay()]
  }`;
}

type StatusTone = "done" | "watch" | "active" | "idle";

/**
 * 计划项状态只表达三件事：做完了、在盯着、还在跑。
 * 契约里 status 是自由字符串，所以按关键片段归类，认不出来就不下结论。
 */
function statusOf(item: DailyPlanItem): { label: string; tone: StatusTone } {
  const value = String(item.status ?? "").toLowerCase();
  if (
    value.includes("succeed") ||
    value.includes("complete") ||
    value === "done"
  ) {
    return { label: "已完成", tone: "done" };
  }
  if (
    item.category === "monitor" ||
    value.includes("monitor") ||
    value.includes("observ")
  ) {
    return { label: "观察中", tone: "watch" };
  }
  if (
    value.includes("run") ||
    value.includes("exec") ||
    value.includes("progress")
  ) {
    return { label: "处理中", tone: "active" };
  }
  return { label: "待开始", tone: "idle" };
}

function PlanItemIcon({
  category,
  tone = "light",
}: {
  category: string;
  tone?: "light" | "dark";
}) {
  const iconProps = {
    size: 18,
    strokeWidth: 1.8,
  } as const;
  if (category === "decision") {
    return <CircleAlert color={colors.amberDot} {...iconProps} />;
  }
  const color = tone === "dark" ? "rgba(255, 255, 255, 0.66)" : colors.grayInk;
  // 与首页同一套「业务对象」语义：库存/订单是箱子，评价是对话气泡。
  if (category === "auto") return <Box color={color} {...iconProps} />;
  if (category === "monitor") {
    return <MessageSquareText color={color} {...iconProps} />;
  }
  return <Clock3 color={color} {...iconProps} />;
}

export function PlanAgenda({
  businessDate,
  decisionCount,
  autoCount,
  monitorCount,
  items,
  timeline = [],
  isLoading,
  hasError,
  onOpenWorkItem,
}: Props) {
  const decisions = items.filter((item) => item.category === "decision");
  const processes = items.filter((item) => item.category !== "decision");
  const resolvedDecisionCount = Math.max(decisionCount, decisions.length);
  const totalCount = resolvedDecisionCount + autoCount + monitorCount;
  const byWorkItem = new Map(
    timeline.map((item) => [item.id, item] as const),
  );
  const dayEndCountdown = untilHour(20);

  return (
    <ScrollView
      style={styles.scroll}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
    >
      <View style={styles.dateRow}>
        <CalendarDays color={colors.muted} size={14} strokeWidth={1.8} />
        <Text style={styles.date}>{formatBusinessDate(businessDate)}</Text>
      </View>
      {isLoading ? (
        <View style={styles.skeleton}>
          <View style={[styles.skeletonLine, styles.skeletonTitle]} />
          <View style={[styles.skeletonLine, styles.skeletonSummary]} />
          <View style={styles.skeletonCard} />
          <View style={styles.skeletonCardSmall} />
        </View>
      ) : (
        <>
          <View style={styles.titleRow}>
            <Text style={styles.title}>今天</Text>
            <Text style={styles.totalCount}>{totalCount} 项安排</Text>
          </View>

          <View style={styles.summaryRow}>
            <View style={styles.summaryDot} />
            <Text style={styles.summaryText}>
              {resolvedDecisionCount} 项要你决定 · {autoCount} 项进行中 ·{" "}
              {monitorCount} 项观察中
            </Text>
          </View>

          {hasError && (
            <View style={styles.notice}>
              <Text style={styles.noticeText}>
                计划暂未同步，当前显示最近一次结果。
              </Text>
            </View>
          )}

          {decisions.length > 0 ? (
            <View style={styles.decisionGroup}>
              {decisions.map((item) => {
                const source = byWorkItem.get(item.work_item_id);
                const remaining = deadlineText(source?.due_at);
                const commerce = commerceLabel(source?.commerce);
                const reason = commerce
                  ? `${item.reason.replace(/[。.]\s*$/, "")} · ${commerce}`
                  : item.reason;
                return (
                  <Pressable
                    key={item.id}
                    accessibilityRole="button"
                    accessibilityLabel={`${item.title}，查看并确认`}
                    onPress={() => onOpenWorkItem(item.work_item_id)}
                    style={({ pressed }) => [
                      styles.decisionCard,
                      pressed && styles.cardPressed,
                    ]}
                  >
                    <View style={styles.decisionTopRow}>
                      <Text style={styles.decisionEyebrow}>优先处理</Text>
                      <Text style={styles.decisionPill}>待你决定</Text>
                    </View>
                    <Text style={styles.decisionTitle}>{item.title}</Text>
                    <Text style={styles.decisionReason}>{reason}</Text>

                    {source?.due_at ? (
                      <TimeAxis
                        startAt={source.occurred_at}
                        dueAt={source.due_at}
                        tone="dark"
                      />
                    ) : null}

                    <View style={styles.decisionFooter}>
                      <View style={styles.decisionAction}>
                        <Text style={styles.decisionActionText}>查看并确认</Text>
                        <ChevronRight
                          color={colors.ink}
                          size={16}
                          strokeWidth={2.2}
                        />
                      </View>
                      {remaining ? (
                        <Text style={styles.decisionRemaining}>{remaining}</Text>
                      ) : null}
                    </View>
                  </Pressable>
                );
              })}
            </View>
          ) : (
            <View style={styles.emptyCard}>
              <CircleAlert
                color={colors.grayInk}
                size={18}
                strokeWidth={1.8}
              />
              <View style={styles.emptyCopy}>
                <Text style={styles.emptyTitle}>今天不需要你介入</Text>
                <Text style={styles.emptyText}>
                  Agent 会继续处理低风险工作。
                </Text>
              </View>
            </View>
          )}

          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Agent 进度</Text>
            <Text style={styles.sectionCount}>
              {autoCount + monitorCount} 项
            </Text>
          </View>

          <View style={styles.progressCard}>
            {processes.map((item, index) => {
              const status = statusOf(item);
              return (
                <Pressable
                  key={item.id}
                  accessibilityRole="button"
                  accessibilityLabel={`${item.title}，${status.label}`}
                  onPress={() => onOpenWorkItem(item.work_item_id)}
                  style={({ pressed }) => [
                    styles.processRow,
                    index === processes.length - 1 && styles.processRowLast,
                    pressed && styles.rowPressed,
                  ]}
                >
                  <View style={styles.processIcon}>
                    <PlanItemIcon category={item.category} />
                  </View>
                  <View style={styles.processCopy}>
                    <Text style={styles.processTitle}>{item.title}</Text>
                    <Text style={styles.processReason} numberOfLines={1}>
                      {item.reason}
                    </Text>
                  </View>
                  <View style={styles.statusCell}>
                    <Text
                      style={[
                        styles.statusLabel,
                        status.tone === "done" && styles.statusLabelDone,
                      ]}
                    >
                      {status.label}
                    </Text>
                    {status.tone === "done" || status.tone === "active" ? (
                      <View
                        style={[
                          styles.statusDot,
                          status.tone === "done"
                            ? styles.statusDotDone
                            : styles.statusDotActive,
                        ]}
                      />
                    ) : null}
                  </View>
                </Pressable>
              );
            })}
          </View>

          {/* 日结不属于 Agent 进度：它是固定时刻的待发生项，单独一行落在卡片外。 */}
          <View style={styles.dayEndRow}>
            {/* 日结还没发生：空心圆表示「未开始」，比任何图标都准确。 */}
            <View style={styles.dayEndRing} />
            <View style={styles.dayEndCopy}>
              <Text style={styles.dayEndTitle}>20:00 日结</Text>
              <Text style={styles.dayEndReason}>
                Agent 整理一天的结果和明日计划
              </Text>
            </View>
            {dayEndCountdown ? (
              <Text style={styles.dayEndCountdown}>{dayEndCountdown}</Text>
            ) : null}
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    paddingHorizontal: 22,
    paddingTop: 16,
    paddingBottom: 80,
  },
  dateRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  date: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 18,
  },
  titleRow: {
    marginTop: 4,
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: 12,
  },
  // 页面标题必须让位给黑卡标题：一屏只允许一个最大字。
  title: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 22,
    lineHeight: 30,
  },
  totalCount: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 17,
  },
  // 计数改成一行文本：三个数字不需要三颗胶囊，设计稿这里是一条状态句。
  summaryRow: {
    marginTop: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
  },
  summaryDot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: colors.amberDot,
  },
  summaryText: {
    flex: 1,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 18,
  },
  notice: {
    marginTop: 14,
    paddingHorizontal: 14,
    paddingVertical: 11,
    borderRadius: radii.small,
    backgroundColor: colors.amber,
  },
  noticeText: {
    color: colors.amberInk,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 18,
  },
  decisionGroup: {
    marginTop: 18,
    gap: 10,
  },
  // 需要人决定的那一项是页面主角，用反相黑卡承载。
  decisionCard: {
    padding: 22,
    borderRadius: radii.hero,
    backgroundColor: colors.black,
    shadowColor: colors.black,
    shadowOffset: { width: 0, height: 14 },
    shadowOpacity: 0.08,
    shadowRadius: 20,
    elevation: 5,
  },
  cardPressed: {
    opacity: 0.94,
  },
  decisionTopRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  decisionEyebrow: {
    color: "rgba(255, 255, 255, 0.5)",
    fontFamily: fonts.medium,
    fontSize: 11,
    lineHeight: 16,
  },
  decisionPill: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    overflow: "hidden",
    borderRadius: radii.pill,
    backgroundColor: colors.amber,
    color: colors.amberInk,
    fontFamily: fonts.semibold,
    fontSize: 11,
    lineHeight: 15,
  },
  decisionTitle: {
    maxWidth: 300,
    marginTop: 14,
    color: colors.white,
    fontFamily: fonts.semibold,
    fontSize: 30,
    lineHeight: 38,
  },
  decisionReason: {
    marginTop: 10,
    color: "rgba(255, 255, 255, 0.62)",
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 19,
    fontVariant: ["tabular-nums"],
  },
  decisionFooter: {
    marginTop: 18,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  decisionAction: {
    minHeight: 44,
    paddingHorizontal: 18,
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: 8,
    borderRadius: radii.pill,
    backgroundColor: colors.white,
  },
  decisionActionText: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 14,
    lineHeight: 20,
  },
  decisionRemaining: {
    color: "rgba(255, 255, 255, 0.55)",
    fontFamily: fonts.medium,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
  },
  emptyCard: {
    marginTop: 18,
    padding: 20,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderRadius: radii.hero,
    backgroundColor: colors.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
  },
  emptyCopy: {
    flex: 1,
    gap: 4,
  },
  emptyTitle: {
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 15,
    lineHeight: 21,
  },
  emptyText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 13,
    lineHeight: 19,
  },
  sectionHeader: {
    minHeight: 22,
    marginTop: 26,
    paddingHorizontal: 2,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  sectionTitle: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 17,
  },
  sectionCount: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 17,
  },
  progressCard: {
    marginTop: 8,
    overflow: "hidden",
    borderRadius: radii.large,
    backgroundColor: colors.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
  },
  processRow: {
    minHeight: 72,
    paddingHorizontal: 18,
    paddingVertical: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  processRowLast: {
    borderBottomWidth: 0,
  },
  rowPressed: {
    backgroundColor: colors.surface,
  },
  // 进度行不套圆形描边容器：设计稿这里图标直接落在白卡上，只有状态用色。
  processIcon: {
    width: 24,
    alignItems: "flex-start",
  },
  processCopy: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  processTitle: {
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 15,
    lineHeight: 21,
  },
  processReason: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 13,
    lineHeight: 18,
  },
  statusCell: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  statusDotDone: {
    backgroundColor: colors.green,
  },
  statusDotActive: {
    backgroundColor: colors.amberDot,
  },
  statusLabel: {
    color: colors.faint,
    fontFamily: fonts.medium,
    fontSize: 12,
  },
  statusLabelDone: {
    color: colors.greenInk,
  },
  // 卡外的日结行：没有底色、没有分割线，只靠 12px 空隙与卡片分开。
  dayEndRow: {
    marginTop: 12,
    minHeight: 56,
    paddingHorizontal: 18,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  dayEndRing: {
    width: 14,
    marginLeft: 5,
    height: 14,
    borderRadius: 7,
    borderWidth: 1,
    borderColor: colors.faint,
  },
  dayEndCopy: {
    flex: 1,
    gap: 3,
  },
  dayEndTitle: {
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 15,
    lineHeight: 21,
    fontVariant: ["tabular-nums"],
  },
  dayEndReason: {
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
  skeleton: {
    paddingTop: 8,
    gap: 12,
  },
  skeletonLine: {
    height: 14,
    borderRadius: 7,
    backgroundColor: colors.line,
  },
  skeletonTitle: {
    width: "42%",
    height: 36,
    borderRadius: 10,
  },
  skeletonSummary: {
    width: "64%",
  },
  skeletonCard: {
    height: 180,
    marginTop: 8,
    borderRadius: 28,
    backgroundColor: colors.line,
  },
  skeletonCardSmall: {
    height: 124,
    borderRadius: 24,
    backgroundColor: colors.line,
  },
});
