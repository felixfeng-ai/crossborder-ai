import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, fonts, type as typeScale } from "@/design/tokens";

type Props = {
  visible: boolean;
  onRetry: () => void;
};

/** 断网横幅：稿上是「琥珀横幅 + 重试」，只提示，不弹窗打断。 */
export function OfflineBanner({ visible, onRetry }: Props) {
  if (!visible) return null;
  return (
    <View accessibilityRole="alert" style={styles.banner}>
      <Text numberOfLines={1} style={styles.text}>
        网络已断开，Agent 仍会继续处理
      </Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="重试连接"
        hitSlop={8}
        onPress={onRetry}
        style={({ pressed }) => [styles.action, pressed && styles.pressed]}
      >
        <Text style={styles.actionText}>重试</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    minHeight: 36,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    backgroundColor: colors.amber,
  },
  text: {
    flex: 1,
    color: colors.amberInk,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 16,
  },
  action: {
    paddingVertical: 4,
    paddingHorizontal: 6,
  },
  actionText: {
    color: colors.amberInk,
    fontFamily: fonts.semibold,
    fontSize: typeScale.caption,
    lineHeight: 16,
  },
  pressed: {
    opacity: 0.55,
  },
});
