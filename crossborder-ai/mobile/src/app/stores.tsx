import { router, useFocusEffect } from "expo-router";
import {
  ChevronRight,
  PackageCheck,
  Plus,
  RefreshCw,
  ShoppingBag,
  Store,
  X,
} from "lucide-react-native";
import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  ApiError,
  PREVIEW_MODE,
  createAmazonConnectUrl,
  createShopifyConnectUrl,
  createTemuConnectUrl,
} from "@/api/client";
import { useCommerceStoresQuery } from "@/api/queries";
import type { CommerceStore } from "@/api/types";
import { ModalScreenHeader } from "@/components/ModalScreenHeader";
import { QueryErrorState } from "@/components/QueryErrorState";
import { colors, fonts, radii, type as typeScale } from "@/design/tokens";
import {
  STORE_PROVIDERS,
  normalizeShopInput,
  storeStatusLabel,
  type StoreProviderId,
} from "@/features/stores/providers";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";

const providerIcons = {
  shopify: ShoppingBag,
  amazon: PackageCheck,
  temu: Store,
} as const;

export default function StoresScreen() {
  const token = useAuthStore((state) => state.token);
  const workspaceId = useWorkspaceStore((state) => state.activeWorkspaceId);
  const effectiveToken = PREVIEW_MODE ? "preview" : token;
  const stores = useCommerceStoresQuery(effectiveToken, workspaceId);
  const refetchStores = stores.refetch;
  const [shopModalOpen, setShopModalOpen] = useState(false);
  const [shopDomain, setShopDomain] = useState("");
  const [connecting, setConnecting] = useState<StoreProviderId | null>(null);
  const [error, setError] = useState("");

  useFocusEffect(
    useCallback(() => {
      if (!PREVIEW_MODE) void refetchStores();
    }, [refetchStores]),
  );

  const openAuthorization = async (url: string) => {
    await Linking.openURL(url);
    setShopModalOpen(false);
    setShopDomain("");
    setConnecting(null);
    if (!PREVIEW_MODE) {
      await stores.refetch();
    }
  };

  const connectProvider = async (provider: StoreProviderId) => {
    if (connecting || !effectiveToken) return;
    if (PREVIEW_MODE) {
      setError("预览模式不会发起真实店铺授权，请安装内测包后操作。");
      return;
    }
    setConnecting(provider);
    setError("");
    try {
      if (provider === "shopify") {
        const shop = normalizeShopInput(shopDomain);
        if (!shop) {
          setError("请输入正确的 Shopify 店铺域名");
          setConnecting(null);
          return;
        }
        const result = await createShopifyConnectUrl(effectiveToken, shop);
        await openAuthorization(result.auth_url);
      } else if (provider === "amazon") {
        const result = await createAmazonConnectUrl(effectiveToken);
        await openAuthorization(result.auth_url);
      } else {
        const result = await createTemuConnectUrl(effectiveToken);
        await openAuthorization(result.auth_url);
      }
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : "暂时无法发起授权，请检查网络和服务商配置。",
      );
      setConnecting(null);
    }
  };

  const connectedStores: CommerceStore[] = stores.data ?? [];

  return (
    <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
      <ModalScreenHeader
        title="店铺与渠道"
        onBack={() => router.back()}
        right={
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="刷新店铺"
            disabled={stores.isFetching}
            onPress={() => void stores.refetch()}
            style={({ pressed }) => [
              styles.refreshButton,
              pressed && styles.pressed,
            ]}
          >
            {stores.isFetching ? (
              <ActivityIndicator color={colors.muted} size="small" />
            ) : (
              <RefreshCw color={colors.inkSoft} size={17} strokeWidth={1.8} />
            )}
          </Pressable>
        }
      />

      {stores.isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.ink} />
        </View>
      ) : stores.isError ? (
        <QueryErrorState
          error={stores.error}
          title="店铺暂时无法同步"
          description="请检查网络后重试，当前不会把失败显示成没有店铺。"
          onRetry={() => void stores.refetch()}
        />
      ) : (
        <ScrollView
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionLabel}>已连接</Text>
            <Text style={styles.sectionCount}>{connectedStores.length}</Text>
          </View>

          <View style={styles.card}>
            {connectedStores.length ? (
              connectedStores.map((store, index) => (
                <View
                  key={`${store.channel_type}:${store.channel_id}`}
                  style={[styles.storeRow, index > 0 && styles.rowDivided]}
                >
                  <View style={styles.storeIcon}>
                    <Store
                      color={colors.mutedStrong}
                      size={17}
                      strokeWidth={1.7}
                    />
                  </View>
                  <View style={styles.storeCopy}>
                    <Text style={styles.storeName} numberOfLines={1}>
                      {store.name}
                    </Text>
                    <Text style={styles.storeMeta}>
                      {store.channel_type.toUpperCase()} ·{" "}
                      {storeStatusLabel(store.status)}
                    </Text>
                  </View>
                </View>
              ))
            ) : (
              <View style={styles.empty}>
                <Text style={styles.emptyTitle}>还没有连接店铺</Text>
                <Text style={styles.emptyText}>
                  连接后，Agent 才能在授权范围内读取和操作店铺。
                </Text>
              </View>
            )}
          </View>

          <Text style={styles.addTitle}>添加店铺</Text>
          <View style={styles.card}>
            {STORE_PROVIDERS.map((provider, index) => {
              const Icon = providerIcons[provider.id];
              return (
                <Pressable
                  key={provider.id}
                  accessibilityRole="button"
                  accessibilityLabel={`连接 ${provider.title}`}
                  disabled={Boolean(connecting)}
                  onPress={() => {
                    setError("");
                    if (provider.id === "shopify") {
                      setShopModalOpen(true);
                    } else {
                      void connectProvider(provider.id);
                    }
                  }}
                  style={({ pressed }) => [
                    styles.providerRow,
                    index > 0 && styles.rowDivided,
                    pressed && styles.pressed,
                  ]}
                >
                  <View style={styles.storeIcon}>
                    <Icon
                      color={colors.mutedStrong}
                      size={17}
                      strokeWidth={1.7}
                    />
                  </View>
                  <View style={styles.storeCopy}>
                    <Text style={styles.providerName}>{provider.title}</Text>
                    <Text style={styles.providerDescription}>
                      {provider.description}
                    </Text>
                  </View>
                  {connecting === provider.id ? (
                    <ActivityIndicator color={colors.muted} size="small" />
                  ) : (
                    <ChevronRight
                      color={colors.faint}
                      size={16}
                      strokeWidth={2}
                    />
                  )}
                </Pressable>
              );
            })}
          </View>

          {!!error && (
            <Text accessibilityLiveRegion="polite" style={styles.error}>
              {error}
            </Text>
          )}
        </ScrollView>
      )}

      <Modal
        transparent
        visible={shopModalOpen}
        animationType="slide"
        onRequestClose={() => setShopModalOpen(false)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setShopModalOpen(false)}
        />
        <SafeAreaView style={styles.sheet} edges={["bottom"]}>
          <View style={styles.sheetHeader}>
            <Text style={styles.sheetTitle}>连接 Shopify</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="关闭 Shopify 连接"
              onPress={() => setShopModalOpen(false)}
              style={styles.sheetClose}
            >
              <X color={colors.inkSoft} size={18} strokeWidth={1.8} />
            </Pressable>
          </View>
          <Text style={styles.sheetText}>
            输入店铺名称或完整域名，下一步将在系统浏览器完成 Shopify 授权。
          </Text>
          <TextInput
            accessibilityLabel="Shopify 店铺域名"
            autoCapitalize="none"
            autoCorrect={false}
            onChangeText={setShopDomain}
            placeholder="demo-store 或 demo-store.myshopify.com"
            placeholderTextColor={colors.faint}
            style={styles.shopInput}
            value={shopDomain}
          />
          <Pressable
            accessibilityRole="button"
            disabled={connecting === "shopify"}
            onPress={() => void connectProvider("shopify")}
            style={({ pressed }) => [
              styles.primaryButton,
              pressed && styles.primaryButtonPressed,
            ]}
          >
            {connecting === "shopify" ? (
              <ActivityIndicator color={colors.white} />
            ) : (
              <>
                <Plus color={colors.white} size={17} strokeWidth={2} />
                <Text style={styles.primaryButtonText}>前往授权</Text>
              </>
            )}
          </Pressable>
          {!!error && <Text style={styles.sheetError}>{error}</Text>}
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 40,
  },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  refreshButton: {
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 22,
  },
  sectionHeader: {
    minHeight: 34,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 4,
  },
  sectionLabel: {
    color: colors.mutedStrong,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 18,
  },
  sectionCount: {
    color: colors.faint,
    fontFamily: fonts.inter,
    fontSize: typeScale.caption,
  },
  card: {
    overflow: "hidden",
    borderRadius: radii.large,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    backgroundColor: colors.card,
  },
  rowDivided: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
  },
  storeRow: {
    minHeight: 66,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  providerRow: {
    minHeight: 70,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  storeIcon: {
    width: 36,
    height: 36,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 18,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    backgroundColor: colors.card,
  },
  storeCopy: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  storeName: {
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: typeScale.body,
    lineHeight: 21,
  },
  storeMeta: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 17,
  },
  providerName: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: typeScale.body,
    lineHeight: 21,
  },
  providerDescription: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 17,
  },
  empty: {
    paddingHorizontal: 18,
    paddingVertical: 24,
    gap: 6,
  },
  emptyTitle: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: typeScale.body,
    lineHeight: 21,
  },
  emptyText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 20,
  },
  addTitle: {
    marginTop: 26,
    marginBottom: 8,
    paddingHorizontal: 4,
    color: colors.mutedStrong,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 18,
  },
  error: {
    marginTop: 14,
    paddingHorizontal: 6,
    color: colors.danger,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 20,
  },
  pressed: {
    opacity: 0.55,
  },
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(10, 13, 18, 0.24)",
  },
  sheet: {
    paddingHorizontal: 22,
    paddingTop: 10,
    paddingBottom: 14,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    backgroundColor: colors.white,
  },
  sheetHeader: {
    minHeight: 50,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  sheetTitle: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 20,
    lineHeight: 28,
  },
  sheetClose: {
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  sheetText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 21,
  },
  shopInput: {
    height: 54,
    marginTop: 16,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: radii.small,
    color: colors.ink,
    fontFamily: fonts.regular,
    fontSize: typeScale.body,
    backgroundColor: colors.surface,
  },
  primaryButton: {
    minHeight: 52,
    marginTop: 20,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    borderRadius: radii.small,
    backgroundColor: colors.black,
  },
  primaryButtonPressed: {
    opacity: 0.9,
  },
  primaryButtonText: {
    color: colors.white,
    fontFamily: fonts.semibold,
    fontSize: typeScale.body,
  },
  sheetError: {
    marginTop: 12,
    color: colors.danger,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 20,
  },
});
