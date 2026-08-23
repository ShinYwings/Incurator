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

  // An AUTO ref's bulky payload is never read back, so persisting it writes and
  // syncs megabytes nothing will ever look at.
  //
  // `buildLLMMessages` skips auto refs outright -- `if (ref.sourceViewType ===
  // "auto") continue;` -- BEFORE it reads any payload, and the next turn rebuilds
  // auto refs fresh from the live context via `buildAutoContextRefs`. The
  // transcript renderer reads only `label` and `imageBase64`.
  //
  // Measured on a 14.52 MB sessions.json (338 of 369 refs were auto):
  // content 5.29 MB, outline 1.90 MB, windowPages 0.60 MB -- 7.79 MB, 54% of the
  // file, written and synced to every device and never looked at again.
  //
  // `imageBase64` is deliberately NOT dropped: the transcript renders it as an
  // inline chip thumbnail, so removing it would take away something visible.
  // That is a user-facing trade and belongs to the retention work.
  //
  // Only the PERSISTED copy loses these. The in-memory ref keeps its payload for
  // the turn it belongs to, because this runs on the way to disk.
  if (next.sourceViewType === "auto") {
    // `content` is REQUIRED on ContextRef, so it is emptied rather than deleted.
    // Making it optional would push `string | undefined` through every consumer
    // for no gain: each one already gates on truthiness (`if (ref.content)`), so
    // "" and undefined behave identically, and "" costs ~14 bytes against the
    // 5.29 MB it replaces.
    next.content = "";
    delete next.outline;
    delete next.windowPages;
  }
  return next;
}

function sanitizeMessageForSync(message: ChatMessage): ChatMessage {
  const revertData = message.revertData?.filter(
    (item) => !isDeviceAbsolutePath(item.filepath)
  );
  return {
    ...message,
    contextRefs: message.contextRefs?.map(sanitizeContextRefForSync),
    revertData,
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
