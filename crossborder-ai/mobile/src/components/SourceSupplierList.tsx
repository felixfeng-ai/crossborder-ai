import {
  CheckCircle2,
  ExternalLink,
  Factory,
  ShieldCheck,
} from "lucide-react-native";
import { useState } from "react";
import {
  Image,
  Linking,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import type {
  SourcingSearchReport,
  SourcingSourceItem,
} from "@/api/types";
import {
  colors,
  fonts,
  radii,
  spacing,
  type as typeScale,
} from "@/design/tokens";

/** 1688 货源候选只提供公开采购线索，采购和付款始终由用户自行确认。 */
export function SourceSupplierList({
  report,
  onUseSource,
}: {
  report: SourcingSearchReport;
  onUseSource: (source: SourcingSourceItem) => void;
}) {
  const items = Array.isArray(report.items) ? report.items : [];
  return (
    <View style={styles.section}>
      <View style={styles.header}>
        <Text style={styles.title}>1688 货源候选</Text>
        <Text style={styles.meta}>
          {report.image_search_used ? "图片相似搜索" : "关键词搜索"} ·{" "}
          {providerLabel(report.provider)} · {report.total_count ?? items.length} 个
        </Text>
        <Text style={styles.meta}>
          观察时间：{formatObservedAt(report.observed_at)}
        </Text>
      </View>
      {!!report.image_fallback_reason && (
        <Text style={styles.notice}>{report.image_fallback_reason}</Text>
      )}
      {!!report.provider_fallback_reason && (
        <Text style={styles.notice}>{report.provider_fallback_reason}</Text>
      )}
      {items.map((item) => (
        <View key={item.item_id} style={styles.item}>
          <View style={styles.itemTop}>
            <SupplierImage uri={item.image_url} />
            <View style={styles.itemCopy}>
              <Pressable
                accessibilityRole="link"
                accessibilityLabel={`在 1688 查看 ${item.title}`}
                hitSlop={8}
                onPress={() => void Linking.openURL(item.url)}
              >
                <Text style={styles.itemTitle} numberOfLines={2}>
                  {item.title}
                </Text>
              </Pressable>
              {!!item.shop_name && (
                <Text style={styles.shop} numberOfLines={1}>
                  {item.shop_name}
                </Text>
              )}
              <View style={styles.tags}>
                {item.is_factory && (
                  <View style={styles.tag}>
                    <Factory color={colors.muted} size={11} />
                    <Text style={styles.tagText}>工厂</Text>
                  </View>
                )}
                {item.factory_inspection && (
                  <View style={styles.tag}>
                    <ShieldCheck color={colors.muted} size={11} />
                    <Text style={styles.tagText}>验厂</Text>
                  </View>
                )}
                {!!item.location && (
                  <Text style={styles.location}>{item.location}</Text>
                )}
              </View>
            </View>
          </View>
          <View style={styles.metrics}>
            <Metric label="采购价" value={item.price || formatPrice(item)} />
            <Metric label="MOQ" value={item.moq != null ? String(item.moq) : "-"} />
            <Metric
              label="销量"
              value={
                item.sale_quantity != null
                  ? formatNumber(item.sale_quantity)
                  : "-"
              }
            />
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="用这个货源算利润"
            onPress={() => onUseSource(item)}
            style={({ pressed }) => [
              styles.useButton,
              pressed && styles.useButtonPressed,
            ]}
          >
            <CheckCircle2 color={colors.white} size={14} />
            <Text style={styles.useButtonText}>用这个货源算利润</Text>
          </Pressable>
        </View>
      ))}
      {items.length === 0 && (
        <Text style={styles.empty}>暂未找到可展示的 1688 货源。</Text>
      )}
      {report.limitations.map((item) => (
        <Text key={item} style={styles.limit}>
          · {item}
        </Text>
      ))}
      <View style={styles.linkHint}>
        <ExternalLink color={colors.muted} size={12} />
        <Text style={styles.linkHintText}>标题可打开 1688 商品详情</Text>
      </View>
    </View>
  );
}

function SupplierImage({ uri }: { uri?: string | null }) {
  const [failed, setFailed] = useState(false);

  if (!uri || failed) {
    return <View style={[styles.image, styles.imageFallback]} />;
  }
  return (
    <Image
      source={{ uri }}
      style={styles.image}
      resizeMode="cover"
      onError={() => setFailed(true)}
    />
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

function providerLabel(provider: string): string {
  if (provider === "justone") return "Just One";
  if (provider === "onebound") return "Onebound";
  return provider;
}

function formatObservedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function formatPrice(item: SourcingSourceItem): string {
  if (item.price_min_cny == null) return "-";
  if (
    item.price_max_cny != null &&
    item.price_max_cny !== item.price_min_cny
  ) {
    return `¥${item.price_min_cny}-${item.price_max_cny}`;
  }
  return `¥${item.price_min_cny}`;
}

function formatNumber(value: number): string {
  return value >= 10000 ? `${(value / 10000).toFixed(1)}万` : String(value);
}

const styles = StyleSheet.create({
  section: {
    gap: spacing.x2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
    paddingTop: spacing.x3,
  },
  header: {
    gap: 2,
  },
  title: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: typeScale.body,
  },
  meta: {
    color: colors.muted,
    fontFamily: fonts.regular,
    fontSize: typeScale.caption,
  },
  notice: {
    color: colors.muted,
    fontFamily: fonts.regular,
    fontSize: typeScale.caption,
    lineHeight: 18,
  },
  item: {
    gap: spacing.x2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.line,
    borderRadius: radii.medium,
    padding: spacing.x2,
  },
  itemTop: {
    flexDirection: "row",
    gap: spacing.x2,
  },
  image: {
    width: 68,
    height: 68,
    borderRadius: radii.small,
    backgroundColor: colors.surfaceQuiet,
  },
  imageFallback: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.line,
  },
  itemCopy: {
    flex: 1,
    gap: 3,
  },
  itemTitle: {
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 19,
  },
  shop: {
    color: colors.muted,
    fontFamily: fonts.regular,
    fontSize: typeScale.caption,
  },
  tags: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 6,
  },
  tag: {
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
  },
  tagText: {
    color: colors.muted,
    fontFamily: fonts.regular,
    fontSize: 11,
  },
  location: {
    color: colors.muted,
    fontFamily: fonts.regular,
    fontSize: 11,
  },
  metrics: {
    flexDirection: "row",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
    paddingTop: spacing.x2,
  },
  metric: {
    flex: 1,
  },
  metricLabel: {
    color: colors.muted,
    fontFamily: fonts.regular,
    fontSize: 11,
  },
  metricValue: {
    marginTop: 2,
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
  },
  useButton: {
    minHeight: 44,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 5,
    borderRadius: radii.small,
    backgroundColor: colors.ink,
  },
  useButtonPressed: {
    opacity: 0.88,
  },
  useButtonText: {
    color: colors.white,
    fontFamily: fonts.semibold,
    fontSize: typeScale.caption,
  },
  empty: {
    color: colors.muted,
    fontFamily: fonts.regular,
    fontSize: typeScale.caption,
    paddingVertical: spacing.x3,
    textAlign: "center",
  },
  limit: {
    color: colors.muted,
    fontFamily: fonts.regular,
    fontSize: 11,
    lineHeight: 16,
  },
  linkHint: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  linkHintText: {
    color: colors.muted,
    fontFamily: fonts.regular,
    fontSize: 11,
  },
});
