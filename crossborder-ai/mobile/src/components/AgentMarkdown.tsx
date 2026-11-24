import { StyleSheet, Text, View } from "react-native";

import {
  parseAgentMarkdown,
  parseInlineMarkdown,
} from "@/features/agent/result-presentation";
import { colors, fonts, type as typeScale } from "@/design/tokens";

/** Agent 结果使用紧凑阅读层级，避免把整份 Markdown 放大成一块黑字。 */
export function AgentMarkdown({ content }: { content: string }) {
  const blocks = parseAgentMarkdown(content);
  return (
    <View style={styles.root}>
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          return (
            <Text key={`${block.type}-${index}`} style={styles.heading}>
              {block.text}
            </Text>
          );
        }
        if (block.type === "ordered" || block.type === "bullet") {
          return (
            <View key={`${block.type}-${index}`} style={styles.listRow}>
              <Text style={styles.marker}>
                {block.type === "ordered" ? `${block.index}.` : "•"}
              </Text>
              <InlineText text={block.text} style={styles.listText} />
            </View>
          );
        }
        return (
          <InlineText
            key={`${block.type}-${index}`}
            text={block.text}
            style={styles.paragraph}
          />
        );
      })}
    </View>
  );
}

function InlineText({
  text,
  style,
}: {
  text: string;
  style: object;
}) {
  return (
    <Text style={style}>
      {parseInlineMarkdown(text).map((segment, index) => (
        <Text
          key={`${index}-${segment.text}`}
          style={segment.bold ? styles.bold : undefined}
        >
          {segment.text}
        </Text>
      ))}
    </Text>
  );
}

const styles = StyleSheet.create({
  root: {
    gap: 10,
  },
  heading: {
    marginTop: 4,
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 17,
    lineHeight: 25,
  },
  paragraph: {
    color: colors.inkSoft,
    fontFamily: fonts.regular,
    fontSize: typeScale.body,
    lineHeight: 24,
  },
  listRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
  },
  marker: {
    minWidth: 18,
    color: colors.faint,
    fontFamily: fonts.inter,
    fontSize: typeScale.meta,
    lineHeight: 24,
    textAlign: "right",
  },
  listText: {
    flex: 1,
    minWidth: 0,
    color: colors.inkSoft,
    fontFamily: fonts.regular,
    fontSize: typeScale.body,
    lineHeight: 24,
  },
  bold: {
    fontFamily: fonts.semibold,
    color: colors.ink,
  },
});
