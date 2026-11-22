import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as ImagePicker from "expo-image-picker";
import { Image } from "expo-image";
import { router } from "expo-router";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react-native";
import { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  API_BASE_URL,
  PREVIEW_MODE,
  deleteImageAsset,
  getImageAssets,
  replaceImageAsset,
  reorderImageAssets,
  updateImageAssetCategory,
  uploadImageAsset,
} from "@/api/client";
import type { ImageAsset, ImageCategory } from "@/api/types";
import { ModalScreenHeader } from "@/components/ModalScreenHeader";
import { PageLoader } from "@/components/PageLoader";
import { QueryErrorState } from "@/components/QueryErrorState";
import { colors, fonts, radii, type as typeScale } from "@/design/tokens";
import { resolveQueryState } from "@/features/query-state/query-state";
import { moveVisibleAsset } from "@/features/library/library-order";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";

const categoryFilters: { key: ImageCategory | null; label: string }[] = [
  { key: null, label: "全部" },
  { key: "product", label: "商品图" },
  { key: "scene", label: "场景图" },
  { key: "photography", label: "摄影" },
];

const categoryLabels: Record<ImageCategory, string> = {
  product: "商品图",
  scene: "场景图",
  photography: "摄影",
  other: "未分类",
};

const previewAssets: ImageAsset[] = [
  {
    id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    name: "收纳包主图",
    url: "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?auto=format&fit=crop&w=900&q=85",
    content_type: "image/webp",
    width: 1200,
    height: 1200,
    file_size: 180000,
    sort_order: 1,
    category: "product",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    name: "旅行场景图",
    url: "https://images.unsplash.com/photo-1553531384-cc64ac80f931?auto=format&fit=crop&w=900&q=85",
    content_type: "image/webp",
    width: 1200,
    height: 1200,
    file_size: 210000,
    sort_order: 2,
    category: "scene",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    name: "细节卖点图",
    url: "https://images.unsplash.com/photo-1622560480605-d83c853bc5c3?auto=format&fit=crop&w=900&q=85",
    content_type: "image/webp",
    width: 1200,
    height: 1200,
    file_size: 196000,
    sort_order: 3,
    category: "photography",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

async function pickImage() {
  const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!permission.granted) {
    Alert.alert("无法打开相册", "请在系统设置中允许访问照片。");
    return null;
  }
  const result = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ["images"],
    quality: 1,
  });
  return result.canceled ? null : result.assets[0];
}

export default function AssetsScreen() {
  const token = useAuthStore((state) => state.token);
  const activeWorkspaceId = useWorkspaceStore(
    (state) => state.activeWorkspaceId,
  );
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const workspaceId = activeWorkspaceId;
  const queryKey = ["mobile", "image-assets", workspaceId];

  const assets = useQuery({
    queryKey,
    enabled: Boolean(workspaceId),
    queryFn: async () => {
      if (PREVIEW_MODE) return previewAssets;
      return getImageAssets(token!, workspaceId!);
    },
  });
  const currentAssets = assets.data ?? [];
  const [filter, setFilter] = useState<ImageCategory | null>(null);
  const visibleAssets = filter
    ? currentAssets.filter((asset) => asset.category === filter)
    : currentAssets;
  const selectedAsset = currentAssets.find(
    (asset) => asset.id === selectedId,
  );

  const invalidateAssets = async () => {
    await queryClient.invalidateQueries({ queryKey });
  };

  const upload = useMutation({
    mutationFn: async () => {
      const asset = await pickImage();
      if (!asset) return null;
      if (PREVIEW_MODE) {
        const previewAsset = {
          ...previewAssets[0],
          id: `preview-${Date.now()}`,
        };
        queryClient.setQueryData<ImageAsset[]>(
          queryKey,
          [...currentAssets, previewAsset],
        );
        return previewAsset;
      }
      return uploadImageAsset(token!, workspaceId!, {
        uri: asset.uri,
        name: asset.fileName ?? "product-image.jpg",
        type: asset.mimeType ?? "image/jpeg",
        file: asset.file,
      });
    },
    onSuccess: async (asset) => {
      if (asset) {
        setSelectedId(asset.id);
        await invalidateAssets();
      }
    },
    onError: () => {
      Alert.alert("上传失败", "图片没有加入素材库，请稍后重试。");
    },
  });

  const replace = useMutation({
    mutationFn: async () => {
      if (!selectedId) return;
      const asset = await pickImage();
      if (!asset) return;
      if (PREVIEW_MODE) return;
      await replaceImageAsset(token!, workspaceId!, selectedId, {
        uri: asset.uri,
        name: asset.fileName ?? "replacement.jpg",
        type: asset.mimeType ?? "image/jpeg",
        file: asset.file,
      });
    },
    onSuccess: invalidateAssets,
    onError: () => {
      Alert.alert("替换失败", "原图片没有受影响，请稍后重试。");
    },
  });

  const remove = useMutation({
    mutationFn: async () => {
      if (!selectedId) return;
      if (!PREVIEW_MODE) {
        await deleteImageAsset(token!, workspaceId!, selectedId);
      }
    },
    onSuccess: async () => {
      setSelectedId(null);
      await invalidateAssets();
    },
    onError: () => {
      Alert.alert("没有移除", "素材库没有发生变化，请稍后重试。");
    },
  });

  const reorder = useMutation({
    mutationFn: async (direction: -1 | 1) => {
      if (!selectedId) return;
      const next = moveVisibleAsset(
        currentAssets,
        visibleAssets.map((asset) => asset.id),
        selectedId,
        direction,
      );
      if (next === currentAssets) return;
      queryClient.setQueryData<ImageAsset[]>(queryKey, next);
      if (!PREVIEW_MODE) {
        await reorderImageAssets(
          token!,
          workspaceId!,
          next.map((asset) => asset.id),
        );
      }
    },
    onError: async () => {
      await invalidateAssets();
      Alert.alert("顺序没有保存", "素材库已恢复原顺序，请重试。");
    },
  });

  const categorize = useMutation({
    mutationFn: async ({
      assetId,
      category,
    }: {
      assetId: string;
      category: ImageCategory;
    }) => {
      queryClient.setQueryData<ImageAsset[]>(queryKey, (previous) =>
        previous?.map((asset) =>
          asset.id === assetId ? { ...asset, category } : asset,
        ),
      );
      if (!PREVIEW_MODE) {
        await updateImageAssetCategory(token!, workspaceId!, assetId, category);
      }
    },
    onSuccess: invalidateAssets,
    onError: async () => {
      await invalidateAssets();
      Alert.alert("分类没有保存", "素材库已恢复原分类，请重试。");
    },
  });

  const confirmCategorize = (asset: ImageAsset) => {
    const options = (
      ["product", "scene", "photography", "other"] as ImageCategory[]
    ).map((category) => ({
      text: categoryLabels[category],
      onPress: () => categorize.mutate({ assetId: asset.id, category }),
    }));
    Alert.alert(
      "归到哪一类",
      `${asset.name} · 分类只用于挑选，不影响历史 Listing 引用。`,
      [...options, { text: "取消", style: "cancel" as const }],
    );
  };

  const confirmDelete = () => {
    Alert.alert("从素材库移除", "历史 Listing 已引用的图片仍会保留。", [
      { text: "取消", style: "cancel" },
      {
        text: "移除",
        style: "destructive",
        onPress: () => remove.mutate(),
      },
    ]);
  };

  const queryState = resolveQueryState({
    isLoading: assets.isLoading,
    isError: assets.isError,
    hasData: Boolean(assets.data),
  });

  if (queryState === "loading") return <PageLoader />;
  if (queryState === "error") {
    return (
      <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
        <ModalScreenHeader title="素材库" onBack={() => router.back()} />
        <QueryErrorState
          title="素材库暂时无法同步"
          description="请恢复网络后重试，当前不会把请求失败显示成空素材库。"
          onRetry={() => void assets.refetch()}
        />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
      <ModalScreenHeader
        title="素材库"
        onBack={() => router.back()}
        right={
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="上传图片"
            disabled={upload.isPending}
            onPress={() => upload.mutate()}
            style={({ pressed }) => [
              styles.headerAction,
              pressed && styles.pressed,
            ]}
          >
            {upload.isPending ? (
              <ActivityIndicator color={colors.ink} size="small" />
            ) : (
              <Plus color={colors.ink} size={19} strokeWidth={1.8} />
            )}
          </Pressable>
        }
      />

      <FlatList
        data={visibleAssets}
        keyExtractor={(asset) => asset.id}
        numColumns={2}
        style={styles.body}
        columnWrapperStyle={styles.row}
        contentContainerStyle={[
          styles.grid,
          visibleAssets.length === 0 && styles.emptyGrid,
        ]}
        refreshing={assets.isRefetching}
        onRefresh={() => void assets.refetch()}
        ListHeaderComponent={
          <View style={styles.filterRow}>
            {categoryFilters.map((item) => {
              const active = filter === item.key;
              const count = item.key
                ? currentAssets.filter((asset) => asset.category === item.key)
                    .length
                : currentAssets.length;
              return (
                <Pressable
                  key={item.label}
                  accessibilityRole="button"
                  accessibilityState={{ selected: active }}
                  accessibilityLabel={`筛选${item.label}`}
                  onPress={() => setFilter(item.key)}
                  style={({ pressed }) => [
                    styles.filterChip,
                    active && styles.filterChipActive,
                    pressed && styles.pressed,
                  ]}
                >
                  <Text
                    style={[
                      styles.filterLabel,
                      active && styles.filterLabelActive,
                    ]}
                  >
                    {item.label}
                  </Text>
                  {count > 0 && (
                    <Text
                      style={[
                        styles.filterCount,
                        active && styles.filterCountActive,
                      ]}
                    >
                      {count}
                    </Text>
                  )}
                </Pressable>
              );
            })}
          </View>
        }
        renderItem={({ item }) => {
          const selected = item.id === selectedId;
          const source = item.url
            ? {
                uri: /^https?:\/\//i.test(item.url)
                  ? item.url
                  : `${API_BASE_URL}${item.url}`,
                headers: token
                  ? { Authorization: `Bearer ${token}` }
                  : undefined,
              }
            : undefined;
          const dimension =
            item.width && item.height
              ? `${item.width}×${item.height}`
              : item.content_type.replace("image/", "").toUpperCase();
          const meta =
            item.category && item.category !== "other"
              ? `${categoryLabels[item.category]} · ${dimension}`
              : dimension;
          return (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`选择 ${item.name}`}
              accessibilityHint="长按可以改分类"
              onPress={() => setSelectedId(selected ? null : item.id)}
              onLongPress={() => confirmCategorize(item)}
              style={({ pressed }) => [
                styles.card,
                selected && styles.cardSelected,
                pressed && styles.pressed,
              ]}
            >
              {source ? (
                <Image
                  source={source}
                  style={styles.image}
                  contentFit="cover"
                />
              ) : (
                <View style={styles.previewPlaceholder} />
              )}
              {selected && (
                <View style={styles.checkBadge}>
                  <Check color={colors.white} size={13} strokeWidth={2.4} />
                </View>
              )}
              <Text style={styles.assetName} numberOfLines={1}>
                {item.name}
              </Text>
              <Text style={styles.assetMeta} numberOfLines={1}>
                {meta}
              </Text>
            </Pressable>
          );
        }}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>
              {filter ? `还没有${categoryLabels[filter]}素材` : "素材库还是空的"}
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={() => upload.mutate()}
              style={({ pressed }) => [
                styles.emptyAction,
                pressed && styles.pressed,
              ]}
            >
              <Plus color={colors.white} size={16} strokeWidth={1.9} />
              <Text style={styles.emptyActionText}>添加图片</Text>
            </Pressable>
          </View>
        }
      />

      {selectedAsset && (
        <View style={styles.toolbar}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="向前移动"
            onPress={() => reorder.mutate(-1)}
            style={({ pressed }) => [
              styles.tool,
              pressed && styles.pressed,
            ]}
          >
            <ChevronLeft color={colors.inkSoft} size={18} strokeWidth={1.8} />
            <Text style={styles.toolLabel}>前移</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="向后移动"
            onPress={() => reorder.mutate(1)}
            style={({ pressed }) => [
              styles.tool,
              pressed && styles.pressed,
            ]}
          >
            <ChevronRight color={colors.inkSoft} size={18} strokeWidth={1.8} />
            <Text style={styles.toolLabel}>后移</Text>
          </Pressable>
          <View style={styles.toolDivider} />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="替换图片"
            disabled={replace.isPending}
            onPress={() => replace.mutate()}
            style={({ pressed }) => [
              styles.tool,
              pressed && styles.pressed,
            ]}
          >
            <RefreshCw color={colors.inkSoft} size={17} strokeWidth={1.8} />
            <Text style={styles.toolLabel}>替换</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="移除图片"
            disabled={remove.isPending}
            onPress={confirmDelete}
            style={({ pressed }) => [
              styles.tool,
              pressed && styles.pressed,
            ]}
          >
            <Trash2 color={colors.danger} size={17} strokeWidth={1.8} />
            <Text style={[styles.toolLabel, styles.toolLabelDanger]}>删除</Text>
          </Pressable>
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.background,
  },
  body: {
    flex: 1,
    backgroundColor: colors.background,
  },
  headerAction: {
    width: 34,
    height: 34,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    borderRadius: 17,
    backgroundColor: colors.card,
  },
  grid: {
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 28,
    gap: 10,
  },
  filterRow: {
    marginHorizontal: -16,
    paddingHorizontal: 16,
    paddingTop: 2,
    paddingBottom: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  filterChip: {
    minHeight: 30,
    paddingHorizontal: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    borderRadius: radii.pill,
    backgroundColor: colors.card,
  },
  filterChipActive: {
    borderColor: colors.ink,
    backgroundColor: colors.ink,
  },
  filterLabel: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 16,
  },
  filterLabelActive: {
    color: colors.white,
  },
  filterCount: {
    color: colors.faint,
    fontFamily: fonts.inter,
    fontSize: 11,
    lineHeight: 14,
  },
  filterCountActive: {
    color: colors.white,
    opacity: 0.62,
  },
  emptyGrid: {
    flexGrow: 1,
  },
  row: {
    gap: 10,
  },
  card: {
    width: "48.5%",
    maxWidth: 180,
    flexGrow: 0,
    flexBasis: "auto",
    minWidth: 0,
    padding: 5,
    gap: 7,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    borderRadius: radii.small,
    backgroundColor: colors.card,
  },
  cardSelected: {
    borderWidth: 1.5,
    borderColor: colors.ink,
  },
  image: {
    width: "100%",
    aspectRatio: 1,
    borderRadius: 8,
    backgroundColor: colors.graySoft,
  },
  previewPlaceholder: {
    width: "100%",
    aspectRatio: 1,
    borderRadius: 8,
    backgroundColor: colors.graySoft,
  },
  assetName: {
    paddingHorizontal: 3,
    color: colors.inkSoft,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 17,
  },
  assetMeta: {
    paddingHorizontal: 3,
    paddingBottom: 3,
    color: colors.faint,
    fontFamily: fonts.inter,
    fontSize: typeScale.caption,
    lineHeight: 16,
  },
  checkBadge: {
    position: "absolute",
    top: 12,
    right: 12,
    width: 22,
    height: 22,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 11,
    backgroundColor: colors.ink,
  },
  empty: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 16,
  },
  emptyTitle: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.body,
    lineHeight: 21,
  },
  emptyAction: {
    minHeight: 44,
    paddingHorizontal: 18,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    borderRadius: radii.pill,
    backgroundColor: colors.ink,
  },
  emptyActionText: {
    color: colors.white,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 18,
  },
  toolbar: {
    marginHorizontal: 16,
    marginBottom: 12,
    minHeight: 62,
    paddingHorizontal: 10,
    paddingVertical: 4,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    borderRadius: radii.pill,
    backgroundColor: colors.card,
  },
  tool: {
    minWidth: 62,
    paddingVertical: 7,
    alignItems: "center",
    justifyContent: "center",
    gap: 3,
    borderRadius: 22,
  },
  toolLabel: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 15,
  },
  toolLabelDanger: {
    color: colors.danger,
  },
  toolDivider: {
    width: StyleSheet.hairlineWidth,
    height: 18,
    marginHorizontal: 3,
    backgroundColor: colors.line,
  },
  pressed: {
    opacity: 0.58,
  },
});
