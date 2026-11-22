import {
  Image as SvgImage,
  Svg,
} from "react-native-svg";

import { signInWordmark } from "@/design/assets";

type Props = {
  width?: number;
};

/**
 * 字标始终通过 SVG 容器渲染，避免 iOS 与 Android 因书法字体缺省而出现差异。
 * 内部素材取自设计定稿，视觉尺寸对应 44pt 光学字号。
 */
export function VeyaShipWordmark({ width = 160 }: Props) {
  const height = (width / 430) * 155;

  return (
    <Svg
      accessibilityLabel="VeyaShip"
      width={width}
      height={height}
      viewBox="0 0 430 155"
    >
      <SvgImage
        href={signInWordmark}
        width={430}
        height={155}
        preserveAspectRatio="xMidYMid meet"
      />
    </Svg>
  );
}
