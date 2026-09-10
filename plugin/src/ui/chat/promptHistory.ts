import type { ChatMessage } from "../../types";

/**
 * A provider turn should carry enough recent dialogue to resolve a follow-up,
 * while the persisted session remains the complete user-visible transcript.
 * Keeping these limits here makes the prompt boundary explicit and testable.
 */
export const PROMPT_HISTORY_MESSAGE_LIMIT = 4;
export const PROMPT_HISTORY_CHAR_LIMIT = 48_000;

type PromptHistoryMessage = Pick<ChatMessage, "role" | "content" | "contextRefs">;

function promptMessageCharCost(message: PromptHistoryMessage): number {
  // Context text is part of the provider payload even though it is stored on
  // the message separately. Count it so an old message with a large pasted
  // passage cannot evade the history budget.
  const contextCost = (message.contextRefs ?? []).reduce(
    (total, ref) => total + ref.label.length + (ref.content?.length ?? 0),
    0
  );
  return message.content.length + contextCost;
}

/**
 * Select a contiguous, chronological suffix for the provider prompt.
 *
 * The newest message is always retained, even when it alone exceeds the
 * budget: dropping the question would produce an answer to an older turn.
 * Older messages are added from newest to oldest until either limit is hit;
 * stopping at the first overflow keeps the retained history contiguous and
 * avoids confusing role order. The input array and its message objects are
 * never mutated.
 */
export function selectPromptHistory<T extends PromptHistoryMessage>(
  messages: readonly T[],
  messageLimit = PROMPT_HISTORY_MESSAGE_LIMIT,
  charLimit = PROMPT_HISTORY_CHAR_LIMIT
): T[] {
  const conversation = messages.filter((message) => message.role !== "system");
  const selected: T[] = [];
  let chars = 0;
  for (let index = conversation.length - 1; index >= 0; index -= 1) {
    if (selected.length >= messageLimit) break;
    const message = conversation[index];
    const cost = promptMessageCharCost(message);
    if (selected.length > 0 && chars + cost > charLimit) break;
    selected.push(message);
    chars += cost;
  }
  return selected.reverse();
}
