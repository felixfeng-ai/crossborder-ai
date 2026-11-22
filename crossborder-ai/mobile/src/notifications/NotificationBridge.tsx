import * as Notifications from "expo-notifications";
import Constants from "expo-constants";
import { useEffect } from "react";
import { Platform } from "react-native";

import { PREVIEW_MODE, registerDevice } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import {
  consumePendingDeepLink,
  navigateDeepLink,
  savePendingDeepLink,
} from "./deepLink";

if (Platform.OS !== "web") {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: false,
      shouldSetBadge: false,
    }),
  });
}

async function registerPushDevice(token: string) {
  if (PREVIEW_MODE) return;
  const permission = await Notifications.requestPermissionsAsync();
  if (!permission.granted) return;
  const projectId =
    Constants.expoConfig?.extra?.eas?.projectId ??
    (Constants as unknown as { easConfig?: { projectId?: string } }).easConfig
      ?.projectId;
  // 没有 EAS projectId 时仍可接收站内通知，避免注册虚假的推送令牌。
  if (!projectId) return;
  const pushToken = await Notifications.getExpoPushTokenAsync({ projectId });
  await registerDevice(token, {
    expo_push_token: pushToken.data,
    platform:
      Platform.OS === "ios"
        ? "ios"
        : Platform.OS === "android"
          ? "android"
          : "web",
    device_name: undefined,
  });
}

export function NotificationBridge() {
  const token = useAuthStore((state) => state.token);
  const hydrated = useAuthStore((state) => state.hydrated);

  useEffect(() => {
    if (!hydrated || PREVIEW_MODE) return;
    const handleResponse = async (
      response: Notifications.NotificationResponse,
    ) => {
      const data = response.notification.request.content.data ?? {};
      const deepLink =
        typeof data.deep_link === "string" ? data.deep_link : null;
      if (!deepLink) return;
      if (token) {
        navigateDeepLink(deepLink);
      } else {
        await savePendingDeepLink(deepLink);
      }
    };
    const subscription =
      Notifications.addNotificationResponseReceivedListener(handleResponse);
    void Notifications.getLastNotificationResponseAsync()
      .then((response) => {
        if (response) void handleResponse(response);
      })
      .catch(() => undefined);
    return () => subscription.remove();
  }, [hydrated, token]);

  useEffect(() => {
    if (!hydrated || !token || PREVIEW_MODE) return;
    void registerPushDevice(token).catch(() => {
      // 推送权限或网络失败不阻塞 App 使用。
    });
  }, [hydrated, token]);

  useEffect(() => {
    if (!hydrated || !token || PREVIEW_MODE) return;
    void consumePendingDeepLink().then((deepLink) => {
      if (deepLink) navigateDeepLink(deepLink);
    });
  }, [hydrated, token]);

  return null;
}
