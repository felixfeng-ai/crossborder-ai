import { useEffect, useState } from "react";
import {
  AccessibilityInfo,
  Animated,
  Easing,
  Image,
  StyleSheet,
  View,
} from "react-native";

import { splashMark } from "@/design/assets";
import { colors } from "@/design/tokens";

/**
 * 原生 Splash 之后的应用接管层。
 * 复用同一品牌标记，避免启动页消失时出现空白或视觉跳变。
 */
export function BrandBootScreen() {
  const [reduceMotion, setReduceMotion] = useState(false);
  const [pulse] = useState(() => new Animated.Value(0.55));

  useEffect(() => {
    let mounted = true;

    void AccessibilityInfo.isReduceMotionEnabled().then((enabled) => {
      if (mounted) setReduceMotion(enabled);
    });
    const subscription = AccessibilityInfo.addEventListener(
      "reduceMotionChanged",
      setReduceMotion,
    );

    return () => {
      mounted = false;
      subscription.remove();
    };
  }, []);

  useEffect(() => {
    if (reduceMotion) {
      pulse.setValue(0.72);
      return;
    }

    const breathing = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: 760,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 0.5,
          duration: 760,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
      ]),
    );
    breathing.start();
    return () => breathing.stop();
  }, [pulse, reduceMotion]);

  return (
    <View style={styles.container}>
      <Image
        source={splashMark}
        style={styles.mark}
        resizeMode="contain"
        accessibilityRole="image"
        accessibilityLabel="VeyaShip"
      />
      <View
        style={styles.track}
        accessible
        accessibilityRole="progressbar"
        accessibilityLabel="VeyaShip 正在加载"
      >
        <Animated.View style={[styles.indicator, { opacity: pulse }]} />
      </View>
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
  mark: {
    width: 128,
    height: 128,
  },
  track: {
    width: 62,
    height: 2,
    marginTop: -2,
    overflow: "hidden",
    borderRadius: 99,
    backgroundColor: "rgba(17, 20, 25, 0.12)",
  },
  indicator: {
    width: 38,
    height: 2,
    borderRadius: 99,
    backgroundColor: colors.ink,
  },
});
