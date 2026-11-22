import { RefreshCw, WifiOff } from "lucide-react-native";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, fonts, radii, type as typeScale } from "@/design/tokens";

type Props = {
  title?: string;
  description?: string;
  onRetry: () => void;
};

export function QueryErrorState({
  title = "暂时无法同步",
  description = "请检查网络后重试，当前页面不会用空数据替代真实状态。",
  onRetry,
}: Props) {
  return (
    <View style={styles.container}>
      <View style={styles.icon}>
        <WifiOff color={colors.mutedStrong} size={22} strokeWidth={1.7} />
      </View>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.description}>{description}</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="重新加载"
        onPress={onRetry}
        style={({ pressed }) => [
          styles.action,
          pressed && styles.pressed,
        ]}
      >
        <RefreshCw color={colors.white} size={15} strokeWidth={1.9} />
        <Text style={styles.actionText}>重新加载</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingHorizontal: 32,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.background,
  },
  icon: {
    width: 52,
    height: 52,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 26,
    backgroundColor: colors.surface,
  },
  title: {
    marginTop: 18,
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: typeScale.body,
    lineHeight: 24,
  },
  description: {
    maxWidth: 280,
    marginTop: 8,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 20,
    textAlign: "center",
  },
  action: {
    minHeight: 44,
    marginTop: 20,
    paddingHorizontal: 18,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    borderRadius: radii.pill,
    backgroundColor: colors.ink,
  },
  actionText: {
    color: colors.white,
    fontFamily: fonts.semibold,
    fontSize: typeScale.meta,
    lineHeight: 18,
  },
  pressed: {
    opacity: 0.62,
  },
});
