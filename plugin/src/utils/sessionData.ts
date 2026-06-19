import type { ChatMessage, ChatSession, ContextRef, SessionData } from "../types";

export function normalizeSessionData(raw: Partial<SessionData> | null | undefined): SessionData {
  return sanitizeSessionDataForSync({
    chatSessions: Array.isArray(raw?.chatSessions) ? raw.chatSessions : [],
    activeChatSessionId: raw?.activeChatSessionId,
    deletedSessionIds: Array.isArray(raw?.deletedSessionIds) ? raw.deletedSessionIds : [],
  });
}

function sessionSortValue(session: ChatSession): number {
  return Number.isFinite(session.updatedAt) ? session.updatedAt : session.createdAt || 0;
}

function preferNewerSession(a: ChatSession, b: ChatSession): ChatSession {
  if (sessionSortValue(a) !== sessionSortValue(b)) {
    return sessionSortValue(a) > sessionSortValue(b) ? a : b;
  }
  return (a.messages?.length || 0) >= (b.messages?.length || 0) ? a : b;
}

export function mergeSessionData(local: SessionData, remote: SessionData): SessionData {
  const sessions = new Map<string, ChatSession>();
  const deletedSessionIds = Array.from(
    new Set([...(remote.deletedSessionIds || []), ...(local.deletedSessionIds || [])])
  );
  const deleted = new Set(deletedSessionIds);

  for (const session of remote.chatSessions) {
    if (session?.id && !deleted.has(session.id)) sessions.set(session.id, session);
  }

  for (const session of local.chatSessions) {
    if (!session?.id || deleted.has(session.id)) continue;
    const existing = sessions.get(session.id);
    sessions.set(session.id, existing ? preferNewerSession(session, existing) : session);
  }

  const chatSessions = Array.from(sessions.values()).sort(
    (a, b) => sessionSortValue(b) - sessionSortValue(a)
  );
  const ids = new Set(chatSessions.map((session) => session.id));
  const activeChatSessionId =
    (local.activeChatSessionId && ids.has(local.activeChatSessionId)
      ? local.activeChatSessionId
      : undefined) ||
    (remote.activeChatSessionId && ids.has(remote.activeChatSessionId)
      ? remote.activeChatSessionId
      : undefined) ||
    chatSessions[0]?.id;

  return sanitizeSessionDataForSync({ chatSessions, activeChatSessionId, deletedSessionIds });
}

function isDeviceAbsolutePath(value: string): boolean {
  return (
    value.startsWith("/") ||
    /^[A-Za-z]:[\\/]/.test(value) ||
    value.startsWith("\\\\")
  );
}

function sanitizeContextRefForSync(ref: ContextRef): ContextRef {
  const next: ContextRef = { ...ref };
  if (typeof next.filePath === "string" && isDeviceAbsolutePath(next.filePath)) {
    delete next.filePath;
  }
  // Backend status is runtime-local and often carries absolute source/current/
  // candidate paths. Persist portable identity on the ContextRef instead.
  delete next.backendStatus;
  return next;
}

function sanitizeMessageForSync(message: ChatMessage): ChatMessage {
  return {
    ...message,
    contextRefs: message.contextRefs?.map(sanitizeContextRefForSync),
  };
}

export function sanitizeSessionDataForSync(data: SessionData): SessionData {
  return {
    ...data,
    chatSessions: data.chatSessions.map((session) => ({
      ...session,
      messages: session.messages.map(sanitizeMessageForSync),
    })),
  };
}
