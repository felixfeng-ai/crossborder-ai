import type { ExpoConfig } from "expo/config";

const linkHost = process.env.EXPO_PUBLIC_APP_LINK_HOST?.trim();
const previewMode = process.env.EXPO_PUBLIC_PREVIEW_MODE === "1";
const requireRemoteApi = process.env.EXPO_PUBLIC_REQUIRE_REMOTE_API === "1";
const configuredApiUrl = process.env.EXPO_PUBLIC_API_URL?.trim();
const localApiUrl = "http://127.0.0.1:8000";

if ((process.env.EAS_BUILD === "true" || requireRemoteApi) && !previewMode) {
  if (!configuredApiUrl) {
    throw new Error(
      "EAS 构建缺少 EXPO_PUBLIC_API_URL。请连接真实 HTTPS API，或使用 ui-preview 构建档位查看界面。",
    );
  }
  let parsedApiUrl: URL;
  try {
    parsedApiUrl = new URL(configuredApiUrl);
  } catch {
    throw new Error("EXPO_PUBLIC_API_URL 必须是完整的 HTTPS 地址。");
  }
  if (parsedApiUrl.protocol !== "https:") {
    throw new Error("真实内测构建的 EXPO_PUBLIC_API_URL 必须使用 HTTPS。");
  }
}

const apiUrl = (configuredApiUrl || localApiUrl).replace(/\/+$/, "");

const config: ExpoConfig = {
  name: "VeyaShip Agent",
  slug: "veyaship-agent",
  owner: "felix-ai",
  version: "1.0.0",
  orientation: "portrait",
  scheme: "veyaship",
  userInterfaceStyle: "light",
  icon: "./assets/icon.png",
  ios: {
    supportsTablet: false,
    bundleIdentifier: "com.veyaship.agent",
    infoPlist: {
      NSMicrophoneUsageDescription:
        "VeyaShip 需要使用麦克风，将你的语音指令交给 Agent 执行。",
      NSCameraUsageDescription:
        "VeyaShip 需要使用相机，将订单、物流或商品图片交给 Agent 处理。",
      NSPhotoLibraryUsageDescription:
        "VeyaShip 需要访问相册，将商品或订单截图交给 Agent 处理。",
    },
    ...(linkHost
      ? {
          associatedDomains: [`applinks:${linkHost}`],
        }
      : {}),
  },
  android: {
    package: "com.veyaship.agent",
    predictiveBackGestureEnabled: true,
    adaptiveIcon: {
      // 前景是白色标记，背景必须用品牌墨色，避免白底白标。
      backgroundColor: "#0B0E12",
      foregroundImage: "./assets/android-icon-foreground.png",
      backgroundImage: "./assets/android-icon-background.png",
      monochromeImage: "./assets/android-icon-monochrome.png",
    },
    ...(linkHost
      ? {
          intentFilters: [
            {
              action: "VIEW",
              autoVerify: true,
              data: [{ scheme: "https", host: linkHost }],
              category: ["BROWSABLE", "DEFAULT"],
            },
          ],
        }
      : {}),
  },
  web: {
    favicon: "./assets/favicon.png",
    bundler: "metro",
    output: "single",
  },
  plugins: [
    "expo-router",
    "expo-asset",
    "expo-font",
    [
      "expo-splash-screen",
      {
        // 启动画面与应用画布使用同一底色，避免冷启动时出现白色闪屏。
        backgroundColor: "#F2F3F5",
        image: "./assets/splash-icon.png",
        imageWidth: 164,
        resizeMode: "contain",
        dark: {
          backgroundColor: "#F2F3F5",
          image: "./assets/splash-icon.png",
        },
      },
    ],
    "expo-secure-store",
    "expo-sqlite",
    [
      "expo-audio",
      {
        microphonePermission:
          "VeyaShip 需要使用麦克风，将你的语音指令交给 Agent 执行。",
      },
    ],
    [
      "expo-image-picker",
      {
        photosPermission:
          "VeyaShip 需要访问相册，将商品或订单截图交给 Agent 处理。",
        cameraPermission:
          "VeyaShip 需要使用相机，将订单、物流或商品图片交给 Agent 处理。",
      },
    ],
    [
      "expo-media-library",
      {
        photosPermission:
          "VeyaShip 需要访问相册，以便保存 Agent 生成的商品视频。",
        savePhotosPermission:
          "VeyaShip 需要把 Agent 生成的商品视频保存到相册。",
        granularPermissions: ["photo", "video"],
      },
    ],
    "expo-notifications",
  ],
  experiments: {
    typedRoutes: true,
  },
  extra: {
    apiUrl,
    previewMode,
    eas: {
      // 固定项目归属，避免内测构建因本地环境变量缺失无法注册推送。
      projectId:
        process.env.EXPO_PUBLIC_EAS_PROJECT_ID?.trim() ||
        "85dd918e-3671-4472-be2b-dcdb951c3930",
    },
  },
};

export default config;
