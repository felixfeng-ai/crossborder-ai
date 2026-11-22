import { StyleSheet, View } from "react-native";
import Svg, { Path } from "react-native-svg";

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
      {/* 96 画布为小尺寸预留内边距，避免 V 在头像里顶满导致品牌标记过重。 */}
      <Svg
        accessibilityElementsHidden
        focusable={false}
        height={size}
        viewBox="0 0 96 96"
        width={size}
      >
        <Path
          d="M31 28 L46 60 L61 28"
          fill="none"
          stroke={colors.white}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={8}
        />
        <Path
          d="M35 76 L61 76"
          fill="none"
          stroke={colors.white}
          strokeLinecap="round"
          strokeWidth={7}
        />
        <Path
          d="M72 11 Q73 17.5 80 20 Q73 22.5 72 29 Q71 22.5 64 20 Q71 17.5 72 11 Z"
          fill={colors.brandStar}
        />
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    overflow: "hidden",
    backgroundColor: colors.black,
  },
});
