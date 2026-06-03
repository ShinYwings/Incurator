import type { ChatSession } from "../types";

const DEFAULT_TITLE = "New chat";
const DEFAULT_MAX_TITLE_LENGTH = 42;

export function deriveChatSessionTitle(
  session: ChatSession,
  maxLength = DEFAULT_MAX_TITLE_LENGTH
): string {
  const firstUserIndex = session.messages.findIndex(
    (msg) => msg.role === "user" && msg.content.trim()
  );

  if (firstUserIndex >= 0) {
    const firstAnswer = session.messages
      .slice(firstUserIndex + 1)
      .find((msg) => msg.role === "assistant" && msg.content.trim());
    const answerTitle = summarizeTitleSource(firstAnswer?.content ?? "", maxLength);
    if (answerTitle) return answerTitle;

    const questionTitle = summarizeTitleSource(session.messages[firstUserIndex].content, maxLength);
    if (questionTitle) return questionTitle;
  }

  return summarizeTitleSource(session.title, maxLength) || DEFAULT_TITLE;
}

export function formatRelativeSessionTime(timestamp: number, now = Date.now()): string {
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "Unknown time";

  const elapsedMs = Math.max(0, now - timestamp);
  const elapsedSeconds = Math.floor(elapsedMs / 1000);
  if (elapsedSeconds < 60) return "Just now";

  const elapsedMinutes = Math.floor(elapsedSeconds / 60);
  if (elapsedMinutes < 60) return `${elapsedMinutes}m ago`;

  const elapsedHours = Math.floor(elapsedMinutes / 60);
  if (elapsedHours < 24) return `${elapsedHours}h ago`;

  const elapsedDays = Math.floor(elapsedHours / 24);
  if (elapsedDays < 7) return `${elapsedDays}d ago`;

  const elapsedWeeks = Math.floor(elapsedDays / 7);
  if (elapsedDays < 30) return `${elapsedWeeks}w ago`;

  const elapsedMonths = Math.floor(elapsedDays / 30);
  if (elapsedDays < 365) return `${elapsedMonths}mo ago`;

  return `${Math.floor(elapsedDays / 365)}y ago`;
}

function summarizeTitleSource(content: string, maxLength: number): string {
  const normalized = normalizeTitleSource(content);
  if (!normalized) return "";
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, Math.max(1, maxLength - 3)).trimEnd()}...`;
}

function normalizeTitleSource(content: string): string {
  const withoutEditBlocks = content.replace(
    /```ai-agent-edit[\s\S]*?```/gi,
    " "
  );
  const withoutCodeBlocks = withoutEditBlocks.replace(/```[\s\S]*?```/g, " ");
  const firstMeaningfulLine = withoutCodeBlocks
    .split(/\r?\n/)
    .map(cleanMarkdownLine)
    .find((line) => line.length > 0);

  if (!firstMeaningfulLine) return "";
  return firstMeaningfulLine.replace(/\s+/g, " ").trim();
}

function cleanMarkdownLine(line: string): string {
  return line
    .replace(/^#{1,6}\s+/, "")
    .replace(/^[-*+]\s+/, "")
    .replace(/^\d+[.)]\s+/, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[*_`~]/g, "")
    .trim();
}
