export type AgentMarkdownBlock =
  | { type: "heading"; text: string }
  | { type: "paragraph"; text: string }
  | { type: "ordered"; index: string; text: string }
  | { type: "bullet"; text: string };

export type AgentInlineSegment = {
  text: string;
  bold: boolean;
};

/** 把 Agent Markdown 解析成 React Native 易渲染的轻量块。 */
export function parseAgentMarkdown(value: string): AgentMarkdownBlock[] {
  const blocks: AgentMarkdownBlock[] = [];
  for (const rawLine of String(value || "").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;
    const heading = line.match(/^#{1,3}\s+(.+)$/);
    if (heading) {
      blocks.push({ type: "heading", text: heading[1].trim() });
      continue;
    }
    const ordered = line.match(/^(\d+)\.\s+(.+)$/);
    if (ordered) {
      blocks.push({
        type: "ordered",
        index: ordered[1],
        text: ordered[2].trim(),
      });
      continue;
    }
    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      blocks.push({ type: "bullet", text: bullet[1].trim() });
      continue;
    }
    blocks.push({ type: "paragraph", text: line });
  }
  return blocks;
}

/** 拆分 **加粗**，避免把原始 Markdown 标记直接显示给用户。 */
export function parseInlineMarkdown(value: string): AgentInlineSegment[] {
  const segments: AgentInlineSegment[] = [];
  const text = String(value || "");
  const pattern = /\*\*(.+?)\*\*/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > cursor) {
      segments.push({
        text: text.slice(cursor, match.index),
        bold: false,
      });
    }
    segments.push({ text: match[1], bold: true });
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), bold: false });
  }
  return segments.length ? segments : [{ text, bold: false }];
}

export function turnNeedsUserInput(
  status: string,
  steps: { status: string }[],
): boolean {
  return (
    status === "waiting_user" ||
    steps.some((step) => step.status === "needs_input")
  );
}

/** 新 Turn 携带上一轮上下文，避免“继续”变成一段失忆的新对话。 */
export function buildAgentFollowUpText({
  previousInput,
  previousResult,
  reply,
}: {
  previousInput?: string | null;
  previousResult?: string | null;
  reply: string;
}): string {
  return [
    "这是同一任务的补充信息，请延续上一轮任务继续处理。",
    `上一轮用户输入：${String(previousInput || "未记录").trim()}`,
    `上一轮结果摘要：${String(previousResult || "未记录").trim().slice(0, 1600)}`,
    `本次补充：${reply.trim()}`,
  ].join("\n");
}
