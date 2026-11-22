import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useFonts } from "expo-font";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { Platform, StyleSheet, View } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { fontsToLoad } from "@/design/assets";
import { colors } from "@/design/tokens";
import { OfflineBanner } from "@/components/OfflineBanner";
import { WorkspaceEventBridge } from "@/components/WorkspaceEventBridge";
import { useNetworkStatus } from "@/features/connectivity/useNetworkStatus";
import { LEGAL_CENTER_PATH } from "@/features/legal/documents";
import { NotificationBridge } from "@/notifications/NotificationBridge";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";

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
  const [fontsLoaded] = useFonts(fontsToLoad);
  const { online, recheck } = useNetworkStatus();

  useEffect(() => {
    void hydrateAuth();
    void hydrateWorkspace();
  }, [hydrateAuth, hydrateWorkspace]);

  if (!fontsLoaded) {
    return <View style={styles.loading} />;
  }

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
  loading: {
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
