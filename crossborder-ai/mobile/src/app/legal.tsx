import { router } from "expo-router";
import {
  Bot,
  ChevronRight,
  Database,
  Flag,
  Mail,
  Scale,
  ShieldCheck,
} from "lucide-react-native";
import type { LucideIcon } from "lucide-react-native";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ModalScreenHeader } from "@/components/ModalScreenHeader";
import { colors, fonts, radii, type as typeScale } from "@/design/tokens";
import {
  LEGAL_DOCUMENTS,
  LEGAL_DOCUMENT_VERSIONS,
  legalDocumentPath,
  type LegalDocument,
  type LegalDocumentId,
} from "@/features/legal/documents";

const documentIcons: Record<LegalDocumentId, LucideIcon> = {
  terms: Scale,
  privacy: ShieldCheck,
  "data-processing": Database,
  "ai-disclosure": Bot,
  security: ShieldCheck,
  report: Flag,
  contact: Mail,
};

function LegalRow({
  document,
  divided,
}: {
  document: LegalDocument;
  divided?: boolean;
}) {
  const Icon = documentIcons[document.id];

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`阅读${document.title}`}
      onPress={() =>
        router.push(
          legalDocumentPath(document.id) as Parameters<typeof router.push>[0],
        )
      }
      style={({ pressed }) => [
        styles.row,
        divided && styles.rowDivided,
        pressed && styles.pressed,
      ]}
    >
      <View style={styles.rowIcon}>
        <Icon color={colors.mutedStrong} size={17} strokeWidth={1.7} />
      </View>
      <View style={styles.rowCopy}>
        <Text style={styles.rowTitle}>{document.title}</Text>
        <Text style={styles.rowDescription}>{document.description}</Text>
      </View>
      <ChevronRight color={colors.faint} size={16} strokeWidth={2} />
    </Pressable>
  );
}

function LegalGroup({
  title,
  documents,
}: {
  title: string;
  documents: LegalDocument[];
}) {
  return (
    <View style={styles.group}>
      <Text style={styles.groupTitle}>{title}</Text>
      <View style={styles.card}>
        {documents.map((document, index) => (
          <LegalRow
            key={document.id}
            document={document}
            divided={index > 0}
          />
        ))}
      </View>
    </View>
  );
}

export default function LegalScreen() {
  const agreements = LEGAL_DOCUMENTS.filter(
    (document) => document.group === "agreements",
  );
  const support = LEGAL_DOCUMENTS.filter(
    (document) => document.group === "support",
  );

  return (
    <SafeAreaView style={styles.safe} edges={["left", "right", "bottom"]}>
      <ModalScreenHeader
        title="法律与隐私"
        variant="close"
        accessibilityLabel="关闭法律与隐私"
        onBack={() => router.back()}
      />

      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.intro}>
          这些说明适用于 VeyaShip App、网页工作台和你授权的店铺操作。
        </Text>

        <LegalGroup title="协议与数据" documents={agreements} />
        <LegalGroup title="安全与支持" documents={support} />

        <Text style={styles.version}>
          服务条款 {LEGAL_DOCUMENT_VERSIONS.terms} · 隐私政策{" "}
          {LEGAL_DOCUMENT_VERSIONS.privacy} · AI 使用说明{" "}
          {LEGAL_DOCUMENT_VERSIONS.aiDisclosure}
        </Text>
      </ScrollView>
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
    paddingTop: 14,
    paddingBottom: 40,
  },
  intro: {
    paddingHorizontal: 4,
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.meta,
    lineHeight: 21,
  },
  group: {
    marginTop: 26,
  },
  groupTitle: {
    paddingHorizontal: 4,
    paddingBottom: 8,
    color: colors.mutedStrong,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 18,
  },
  card: {
    overflow: "hidden",
    borderRadius: radii.large,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    backgroundColor: colors.card,
  },
  row: {
    minHeight: 70,
    paddingHorizontal: 16,
    paddingVertical: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  rowDivided: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
  },
  rowIcon: {
    width: 34,
    height: 34,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 17,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.cardBorder,
    backgroundColor: colors.card,
  },
  rowCopy: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  rowTitle: {
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: typeScale.body,
    lineHeight: 21,
  },
  rowDescription: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: typeScale.caption,
    lineHeight: 17,
  },
  pressed: {
    opacity: 0.55,
  },
  version: {
    marginTop: 24,
    paddingHorizontal: 12,
    color: colors.faint,
    fontFamily: fonts.medium,
    fontSize: 11,
    lineHeight: 18,
    textAlign: "center",
  },
});
