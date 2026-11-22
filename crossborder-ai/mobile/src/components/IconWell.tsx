import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";

import { colors } from "@/design/tokens";

type Props = {
  children: ReactNode;
  /** 首页/计划页统一 34，密集列表可收到 32。 */
  size?: number;
};

/**
 * 图标容器：白底 + 一圈发丝描边，不填色。
 *
 * 全 App 只有这一种图标「底座」。填色或加投影都会让它和状态色抢注意力，
 * 而图标本身只负责「这是什么对象」，不负责「有多要紧」。
 */
export function IconWell({ children, size = 34 }: Props) {
  return (
    <View
      style={[
        styles.well,
        { width: size, height: size, borderRadius: size / 2 },
      ]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  well: {
    alignItems: "center",
    justifyContent: "center",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    backgroundColor: colors.card,
  },
});
