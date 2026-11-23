import { Image } from "expo-image";
import { useState } from "react";
import { StyleSheet, View } from "react-native";
import Svg, { Path } from "react-native-svg";

import { API_BASE_URL } from "@/api/client";
import { colors } from "@/design/tokens";

type Props = {
  size?: number;
  uri?: string | null;
  headers?: Record<string, string>;
};

function resolveAvatarUrl(uri: string) {
  if (/^https?:\/\//i.test(uri)) return uri;
  return `${API_BASE_URL}${uri.startsWith("/") ? "" : "/"}${uri}`;
}

export function AgentAvatar({
  size = 38,
  uri,
  headers,
}: Props) {
  const [failedUri, setFailedUri] = useState<string | null>(null);

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
      {uri && failedUri !== uri ? (
        <Image
          accessibilityLabel="用户头像"
          contentFit="cover"
          onError={() => setFailedUri(uri)}
          source={{
            uri: resolveAvatarUrl(uri),
            headers,
          }}
          style={StyleSheet.absoluteFill}
          transition={120}
        />
      ) : (
        <Svg
          accessibilityElementsHidden
          focusable={false}
          height={size}
          viewBox="0 0 96 96"
          width={size}
        >
          {/* 96 画布为小尺寸预留内边距，避免 V 在头像里顶满。 */}
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
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    overflow: "hidden",
    backgroundColor: colors.black,
  },
});
