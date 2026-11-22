import {
  Activity,
  Box,
  Check,
  ChevronRight,
  MessageSquareText,
  Tag,
} from "lucide-react-native";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";

import { colors, fonts } from "@/design/tokens";
import { thumbnailsOf } from "@/features/commerce/labels";
import { relativePast } from "@/features/time/relative";

type Props = {
  title: string;
  detail: string;
  onPress: () => void;
  last?: boolean;
  kind?: string;
  occurredAt?: string;
  thumbnails?: string[];
};

/**
 * 图标只按「业务对象」分类，不按优先级分类：
 * 评价是对话气泡（带两条线，和设计稿同款）、Listing 是吊牌、库存和订单是立方体箱子、Agent 动作是勾。
 * 同类对象在任何页面都用同一个图标，用户靠形状就能认出这是什么。
 */
function TaskIcon({ kind }: { kind?: string }) {
  const iconProps = {
    color: colors.mutedStrong,
    size: 17,
    strokeWidth: 1.7,
  };
  if (kind === "customer_reply") return <MessageSquareText {...iconProps} />;
  if (kind === "listing_action") return <Tag {...iconProps} />;
  if (kind === "inventory_update" || kind === "inventory_action") {
    return <Box {...iconProps} />;
  }
  if (kind === "agent_action") return <Check {...iconProps} />;
  if (kind === "order_exception") return <Box {...iconProps} />;
  return <Activity {...iconProps} />;
}

export function QuietTaskRow({
  title,
  detail,
  onPress,
  last,
  kind,
  occurredAt,
  thumbnails,
}: Props) {
  const time = relativePast(occurredAt);
  const shots = thumbnailsOf(thumbnails);
  // 相对时间跟在说明后面，不占独立一列：设计稿里它属于这句描述的一部分。
  const detailText = [detail.replace(/[。.]\s*$/, ""), time]
    .filter(Boolean)
    .join(" · ");

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${title}，${detail}${time ? `，${time}` : ""}`}
      onPress={onPress}
      style={({ pressed }) => [
        styles.row,
        !last && styles.divider,
        pressed && styles.pressed,
      ]}
    >
      <View style={styles.iconWell}>
        <TaskIcon kind={kind} />
      </View>
      <View style={styles.copy}>
        <Text style={styles.title} numberOfLines={1}>
          {title}
        </Text>
        <Text style={styles.detail} numberOfLines={1}>
          {detailText}
        </Text>
      </View>
      {shots.length > 0 ? (
        <View style={styles.thumbs}>
          {shots.map((uri, index) => (
            <Image
              key={uri}
              source={{ uri }}
              style={[styles.thumb, index > 0 && styles.thumbOverlap]}
            />
          ))}
        </View>
      ) : null}
      <ChevronRight color={colors.faint} size={15} strokeWidth={2} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    minHeight: 64,
    paddingVertical: 9,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  divider: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.cardBorder,
  },
  pressed: {
    opacity: 0.55,
  },
  /**
   * 圆形描边容器只用来「框住」线性图标，不填色。
   * 填充色图标底会和状态抢注意力，这是设计稿里唯一的圆形元素。
   */
  iconWell: {
    width: 34,
    height: 34,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 17,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    backgroundColor: colors.card,
  },
  copy: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  title: {
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 15,
    lineHeight: 21,
  },
  detail: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 18,
    fontVariant: ["tabular-nums"],
  },
  // 三张图轻微咬合，白色描边当分隔线，比留空隙更紧凑也更像商品串。
  thumbs: {
    flexDirection: "row",
    alignItems: "center",
  },
  thumb: {
    width: 38,
    height: 38,
    borderRadius: 9,
    borderWidth: 1,
    borderColor: colors.card,
    backgroundColor: colors.graySoft,
  },
  thumbOverlap: {
    marginLeft: -8,
  },
});
