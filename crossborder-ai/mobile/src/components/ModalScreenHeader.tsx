import { ChevronLeft, X } from "lucide-react-native";
import type { ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fonts } from "@/design/tokens";

type Props = {
  title: string;
  onBack: () => void;
  accessibilityLabel?: string;
  variant?: "back" | "close" | "dismiss";
  right?: ReactNode;
};

export function ModalScreenHeader({
  title,
  onBack,
  accessibilityLabel = "返回",
  variant = "back",
  right,
}: Props) {
  // 导航层自己吃状态栏高度：白底从屏幕顶一路铺到标题行底，页面里只用灰内容。
  const insets = useSafeAreaInsets();
  const closeIcon = variant === "close" || variant === "dismiss";
  const action = (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      hitSlop={4}
      onPress={onBack}
      style={({ pressed }) => [
        styles.iconButton,
        pressed && styles.pressed,
      ]}
    >
      <X
        color={colors.inkSoft}
        size={18}
        strokeWidth={1.9}
      />
    </Pressable>
  );
  const backAction = (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="返回"
      hitSlop={4}
      onPress={onBack}
      style={({ pressed }) => [
        styles.iconButton,
        pressed && styles.pressed,
      ]}
    >
      <ChevronLeft color={colors.inkSoft} size={22} strokeWidth={2.1} />
    </Pressable>
  );

  return (
    <View style={[styles.nav, { paddingTop: insets.top }]}>
      {variant === "close" ? <View style={styles.side} /> : backAction}
      <Text style={styles.title}>{title}</Text>
      <View style={right ? styles.sideRight : styles.side}>
        {closeIcon ? action : right}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  nav: {
    minHeight: 48,
    paddingHorizontal: 8,
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.card,
  },
  iconButton: {
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 22,
  },
  title: {
    flex: 1,
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 15,
    lineHeight: 20,
    textAlign: "center",
  },
  side: {
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  // 右侧有文字按钮（如「全部已读」）时按内容宽度放开，避免挤成两行。
  sideRight: {
    minWidth: 44,
    height: 44,
    paddingRight: 4,
    alignItems: "center",
    justifyContent: "center",
  },
  pressed: {
    backgroundColor: colors.surface,
  },
});
