import { Image } from "expo-image";
import { StyleSheet, View } from "react-native";

import { brandMark } from "@/design/assets";
import { colors } from "@/design/tokens";

type Props = {
  size?: number;
};

export function AgentAvatar({ size = 38 }: Props) {
  return (
    <View
      style={[
        styles.frame,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
        },
      ]}
    >
      <Image
        source={brandMark}
        style={{ width: size, height: size }}
        contentFit="cover"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    overflow: "hidden",
    backgroundColor: colors.black,
  },
});
