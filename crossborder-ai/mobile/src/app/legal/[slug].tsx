import { router, useLocalSearchParams, type Href } from "expo-router";
import { Mail } from "lucide-react-native";
import { Alert, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ModalScreenHeader } from "@/components/ModalScreenHeader";
import { colors, fonts, radii, type as typeScale } from "@/design/tokens";
import {
  getLegalDocumentContent,
  legalContactUrl,
  type LegalDocumentContent,
} from "@/features/legal/document-content";
import type { LegalDocumentId } from "@/features/legal/documents";

function renderDate(value: string) {
  const [year, month, day] = value.split("-");
  return `${year} 年 ${Number(month)} 月 ${Number(day)} 日`;
}

function Section({ section }: { section: LegalDocumentContent["sections"][number] }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{section.title}</Text>
      {section.paragraphs.map((paragraph) => (
        <Text key={paragraph} style={styles.paragraph}>
          {paragraph}
        </Text>
      ))}
      {section.bullets?.length ? (
        <View style={styles.bulletList}>
          {section.bullets.map((bullet) => (
            <View key={bullet} style={styles.bulletRow}>
              <View style={styles.bulletDot} />
              <Text style={styles.bulletText}>{bullet}</Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

export default function LegalDocumentScreen() {
  const params = useLocalSearchParams<{ slug?: string }>();
  let document: LegalDocumentContent | null = null;

  try {
    document = getLegalDocumentContent(
      String(params.slug) as LegalDocumentId,
    );
  } catch {
    document = null;
  }

  const sendEmail = async () => {
    if (!document) return;
    try {
      await Linking.openURL(
        legalContactUrl(`${document.shortTitle} · VeyaShip App`),
      );
    } catch {
      Alert.alert("暂时无法打开邮件", "请稍后重试。");
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
      <ModalScreenHeader
        title={document?.shortTitle ?? "法律与隐私"}
        onBack={() => router.back()}
      />

      {document ? (
        <ScrollView
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.sheet}>
            <Text style={styles.title}>{document.title}</Text>
            <Text style={styles.summary}>{document.summary}</Text>
            <Text style={styles.meta}>
              版本 {document.version} · 生效于 {renderDate(document.effectiveDate)}
            </Text>

            {document.sections.map((section) => (
              <Section key={section.id} section={section} />
            ))}
          </View>

          <Pressable
            accessibilityRole="button"
            accessibilityLabel="发送邮件联系 VeyaShip"
            onPress={() => void sendEmail()}
            style={({ pressed }) => [
              styles.emailButton,
              pressed && styles.emailButtonPressed,
            ]}
          >
            <Mail color={colors.white} size={17} strokeWidth={1.8} />
            <Text style={styles.emailButtonText}>发送邮件</Text>
          </Pressable>

          <Text style={styles.footerMeta}>
            {document.shortTitle} · 版本 {document.version}
          </Text>
        </ScrollView>
      ) : (
        <View style={styles.missing}>
          <Text style={styles.missingTitle}>没有找到这份说明</Text>
          <Text style={styles.missingText}>返回法律与隐私中心重新选择。</Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => router.replace("/legal" as Href)}
            style={styles.missingButton}
          >
            <Text style={styles.missingButtonText}>返回法律与隐私</Text>
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
  content: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 40,
  },
  sheet: {
    paddingHorizontal: 20,
    paddingTop: 22,
    paddingBottom: 8,
    borderRadius: radii.large,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    backgroundColor: colors.card,
  },
  title: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: typeScale.cardTitleCompact,
    lineHeight: 34,
  },
  summary: {
    marginTop: 10,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 21,
  },
  meta: {
    marginTop: 14,
    color: colors.faint,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 18,
  },
  section: {
    marginTop: 24,
    paddingTop: 22,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
  },
  sectionTitle: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 17,
    lineHeight: 25,
  },
  paragraph: {
    marginTop: 12,
    color: colors.inkSoft,
    fontFamily: fonts.regular,
    fontSize: typeScale.body,
    lineHeight: 26,
  },
  bulletList: {
    marginTop: 12,
    gap: 9,
  },
  bulletRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
  },
  bulletDot: {
    width: 4,
    height: 4,
    marginTop: 10,
    borderRadius: 2,
    backgroundColor: colors.mutedStrong,
  },
  bulletText: {
    flex: 1,
    color: colors.inkSoft,
    fontFamily: fonts.regular,
    fontSize: typeScale.body,
    lineHeight: 24,
  },
  emailButton: {
    minHeight: 52,
    marginTop: 20,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    borderRadius: radii.small,
    backgroundColor: colors.black,
  },
  emailButtonPressed: {
    opacity: 0.9,
  },
  emailButtonText: {
    color: colors.white,
    fontFamily: fonts.semibold,
    fontSize: typeScale.body,
    lineHeight: 22,
  },
  footerMeta: {
    marginTop: 18,
    color: colors.faint,
    fontFamily: fonts.medium,
    fontSize: 11,
    lineHeight: 18,
    textAlign: "center",
  },
  missing: {
    flex: 1,
    paddingHorizontal: 28,
    alignItems: "center",
    justifyContent: "center",
  },
  missingTitle: {
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: typeScale.pageTitle,
    lineHeight: 30,
  },
  missingText: {
    marginTop: 8,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 21,
    textAlign: "center",
  },
  missingButton: {
    minHeight: 44,
    marginTop: 20,
    paddingHorizontal: 18,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radii.small,
    backgroundColor: colors.black,
  },
  missingButtonText: {
    color: colors.white,
    fontFamily: fonts.semibold,
    fontSize: typeScale.meta,
  },
});
