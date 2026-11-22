import { Path, Svg } from "react-native-svg";

import {
  WORDMARK_ASPECT,
  WORDMARK_PATH,
  WORDMARK_VIEWBOX,
} from "@/design/wordmark-path";

type Props = {
  width?: number;
  fill?: string;
};

/**
 * 字标是真正的矢量路径（Inter 600，字距 -1%），不再是以位图包一层 SVG 的壳，
 * 也不依赖设备字体，因此任意宽度下边缘都是干净的，iOS 与 Android 完全一致。
 */
export function VeyaShipWordmark({ width = 168, fill = "#111213" }: Props) {
  const height = width / WORDMARK_ASPECT;

  return (
    <Svg
      accessibilityLabel="VeyaShip"
      width={width}
      height={height}
      viewBox={WORDMARK_VIEWBOX}
    >
      <Path d={WORDMARK_PATH} fill={fill} />
    </Svg>
  );
}
