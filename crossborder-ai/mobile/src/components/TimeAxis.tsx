import { StyleSheet, Text, View } from "react-native";
import Svg, {
  Circle,
  Defs,
  LinearGradient,
  Rect,
  Stop,
} from "react-native-svg";

import { colors, fonts } from "@/design/tokens";
import { clockOf, spanRatio } from "@/features/time/relative";

type Props = {
  startAt: string;
  dueAt: string;
  tone?: "dark" | "light";
};

/**
 * 时效时间轴：起点取自 occurred_at，终点取自 due_at，橙色圆点表示「现在」。
 *
 * 圆点之前的线段用「白 → 琥珀」渐变填充，表示这段时效已经消耗掉；
 * 圆点之后保持暗色，表示还没走完。这是时间流逝比例，不是任务完成度 ——
 * 契约里没有进度字段，所以只看它会有「时间在逼近截止」的压迫感，
 * 不会被误导成「任务已经做完了一半」。
 */
export function TimeAxis({ startAt, dueAt, tone = "dark" }: Props) {
  const ratio = spanRatio(startAt, dueAt);
  const start = clockOf(startAt);
  const due = clockOf(dueAt);

  if (ratio === null || !start || !due) return null;

  const isDark = tone === "dark";
  const trackColor = isDark ? "rgba(255, 255, 255, 0.14)" : colors.timelineTrack;
  const fillFrom = isDark ? colors.white : colors.timelineStart;
  const fillTo = colors.amberDot;
  const labelColor = isDark ? "rgba(255, 255, 255, 0.44)" : colors.faint;
  const dotX = `${ratio * 100}%`;

  return (
    <View style={styles.wrap}>
      <Svg width="100%" height={13}>
        <Defs>
          <LinearGradient id="axisFill" x1="0" y1="0" x2="1" y2="0">
            <Stop offset="0" stopColor={fillFrom} />
            <Stop offset="1" stopColor={fillTo} />
          </LinearGradient>
        </Defs>

        <Rect x={0} y={4.5} width="100%" height={3} rx={1.5} fill={trackColor} />
        <Rect
          x={0}
          y={4.5}
          width={`${ratio * 100}%`}
          height={3}
          rx={1.5}
          fill="url(#axisFill)"
        />

        {/* 起点：实心白点，标明时效从这里开始计时。 */}
        <Circle cx={2} cy={6} r={3} fill={fillFrom} />

        {/* 现在：外圈光晕 + 实心圆点，一眼看到「时间走到哪」。 */}
        <Circle cx={dotX} cy={6} r={6.5} fill={fillTo} opacity={0.2} />
        <Circle cx={dotX} cy={6} r={4} fill={fillTo} />
      </Svg>

      <View style={styles.labelRow}>
        <Text style={[styles.label, { color: labelColor }]}>{start}</Text>
        <Text style={[styles.label, { color: labelColor }]}>{due}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  // 轴与刻度是一整块，压到 34px 以内，别把黑卡撑高。
  wrap: {
    marginTop: 8,
  },
  labelRow: {
    marginTop: 0,
    flexDirection: "row",
    justifyContent: "space-between",
  },
  // 两端时刻是轴的一部分，必须比正文更弱，允许低于 caption 档。
  label: {
    fontFamily: fonts.inter,
    fontSize: 10,
    lineHeight: 12,
    fontVariant: ["tabular-nums"],
  },
});
