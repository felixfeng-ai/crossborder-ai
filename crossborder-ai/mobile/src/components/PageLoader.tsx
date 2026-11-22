import { ActivityIndicator, StyleSheet, View } from "react-native";

import { colors } from "@/design/tokens";

export function PageLoader() {
  return (
    <View style={styles.container}>
      <ActivityIndicator color={colors.ink} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.background,
  },
});
