import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useFonts } from "expo-font";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { Platform, StyleSheet, View } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { BrandBootScreen } from "@/components/BrandBootScreen";
import { fontsToLoad } from "@/design/assets";
import { isStartupReady } from "@/design/startup-state";
import { colors } from "@/design/tokens";
import { OfflineBanner } from "@/components/OfflineBanner";
import { WorkspaceEventBridge } from "@/components/WorkspaceEventBridge";
import { useNetworkStatus } from "@/features/connectivity/useNetworkStatus";
import { LEGAL_CENTER_PATH } from "@/features/legal/documents";
import { NotificationBridge } from "@/notifications/NotificationBridge";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";

if (Platform.OS !== "web") {
  // 原生启动图保持到字体和本地状态准备完成，避免露出中间空白页。
  void SplashScreen.preventAutoHideAsync().catch(() => undefined);
  SplashScreen.setOptions({ duration: 180, fade: true });
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});

export default function RootLayout() {
  const hydrateAuth = useAuthStore((state) => state.hydrate);
  const hydrateWorkspace = useWorkspaceStore((state) => state.hydrate);
  const [coreHydrated, setCoreHydrated] = useState(false);
  const [fontsLoaded, fontError] = useFonts(fontsToLoad);
  const { online, recheck } = useNetworkStatus();

  useEffect(() => {
    let mounted = true;
    void Promise.allSettled([hydrateAuth(), hydrateWorkspace()]).finally(() => {
      if (mounted) setCoreHydrated(true);
    });

    return () => {
      mounted = false;
    };
  }, [hydrateAuth, hydrateWorkspace]);

  const startupReady = isStartupReady({
    fontsLoaded,
    fontFailed: Boolean(fontError),
    coreHydrated,
  });

  useEffect(() => {
    if (startupReady && Platform.OS !== "web") {
      void SplashScreen.hideAsync().catch(() => undefined);
    }
  }, [startupReady]);

  if (!startupReady) return <BrandBootScreen />;

  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <WorkspaceEventBridge />
          <NotificationBridge />
          <StatusBar style="dark" />
          <View style={[styles.shell, Platform.OS === "web" && styles.webShell]}>
            <OfflineBanner visible={!online} onRetry={recheck} />
            <Stack
              screenOptions={{
                headerShown: false,
                contentStyle: { backgroundColor: colors.background },
                animation: "slide_from_right",
              }}
            >
              <Stack.Screen name="index" />
              <Stack.Screen name="sign-in" />
              <Stack.Screen name="task/[workItemId]" />
              <Stack.Screen name="t/[taskId]" />
              <Stack.Screen name="agent/[turnId]" />
              <Stack.Screen
                name="functions"
                options={{
                  presentation: "modal",
                  animation: "slide_from_bottom",
                }}
              />
              <Stack.Screen name="plan" />
              <Stack.Screen
                name="activity"
                options={{
                  presentation: "modal",
                  animation: "slide_from_bottom",
                }}
              />
              <Stack.Screen
                name="notification-settings"
                options={{
                  presentation: "modal",
                  animation: "slide_from_bottom",
                }}
              />
              <Stack.Screen name="stores" />
              <Stack.Screen
                name={LEGAL_CENTER_PATH}
                options={{
                  presentation: "modal",
                  animation: "slide_from_bottom",
                }}
              />
              <Stack.Screen
                name="legal/[slug]"
                options={{ animation: "slide_from_right" }}
              />
              <Stack.Screen
                name="account"
                options={{
                  presentation: "modal",
                  animation: "slide_from_bottom",
                }}
              />
            </Stack>
          </View>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.background,
  },
  shell: {
    flex: 1,
    width: "100%",
  },
  webShell: {
    maxWidth: 390,
    alignSelf: "center",
    overflow: "hidden",
  },
});
