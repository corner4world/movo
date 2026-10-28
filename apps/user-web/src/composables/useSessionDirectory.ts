import { nextTick, type Ref } from 'vue'
import { deleteSession, listSessionsPaged, updateSessionTitle, type SessionSearchResult, type SessionSummary } from '../api/sessions'
import { t } from './i18n'

type SessionDirectoryOptions = {
  sessions: Ref<SessionSummary[]>
  sessionsLoading: Ref<boolean>
  sessionsLoadingMore: Ref<boolean>
  sessionsHasMore: Ref<boolean>
  sharedSessions: Ref<SessionSummary[]>
  sharedSessionsLoading: Ref<boolean>
  sharedSessionsLoadingMore: Ref<boolean>
  sharedSessionsHasMore: Ref<boolean>
  sessionSearchResults: Ref<SessionSearchResult[]>
  deletingSessionId: Ref<string | null>
  pendingDeleteSession: Ref<SessionSummary | SessionSearchResult | null>
  editingSessionId: Ref<string | null>
  editingSessionTitle: Ref<string>
  renamingSessionId: Ref<string | null>
  authToken: Ref<string>
  canUseCode: Ref<boolean>
  pageSize: number
  getUserId: () => string | null
  getMainId: () => string
  refreshWorkspaceTitles: () => unknown
  sessionIsRunningLocally: (sessionId: string) => boolean
  sessionIsUnreadLocally: (sessionId: string) => boolean
  needsAssistanceLocally: (sessionId: string) => boolean
  hasActiveIntervention: (sessionId: string) => boolean
  removeSession: (sessionId: string) => unknown
  syncActiveRuns: (sessions: SessionSummary[], userId: string) => unknown
}

export function useSessionDirectory(options: SessionDirectoryOptions) {
  const {
    sessions, sessionsLoading, sessionsLoadingMore, sessionsHasMore,
    sharedSessions, sharedSessionsLoading, sharedSessionsLoadingMore, sharedSessionsHasMore,
    sessionSearchResults, deletingSessionId, pendingDeleteSession,
    editingSessionId, editingSessionTitle, renamingSessionId,
    authToken, canUseCode, pageSize: sessionPageSize, getUserId, getMainId,
  } = options

  function mergeSessionPages(existing: SessionSummary[], incoming: SessionSummary[]) {
    const merged = [...existing]
    const seen = new Set(existing.map((item) => item.id))
    for (const item of incoming) {
      if (seen.has(item.id)) continue
      merged.push(item)
      seen.add(item.id)
    }
    return merged
  }

  function sessionIsRunning(sessionId: string) {
    const serverRunning = sessions.value.some((item) => item.id === sessionId && item.active_run?.status === 'running')
    return serverRunning || options.sessionIsRunningLocally(sessionId)
  }

  function sessionScheduledIsRunning(sessionId: string) {
    return sessions.value.some(
      (item) => item.id === sessionId && item.active_run?.source === 'scheduled' && item.active_run?.status === 'running',
    )
  }

  function sessionNeedsHumanAssistance(sessionId: string) {
    const serverNeedsHelp = sessions.value.some(
      (item) => item.id === sessionId
        && (item.active_run?.status === 'suspended' || Number(item.pending_approval_count || 0) > 0),
    )
    return serverNeedsHelp || options.needsAssistanceLocally(sessionId) || options.hasActiveIntervention(sessionId)
  }

  function sessionIsUnread(sessionId: string) {
    return sessions.value.some((item) => item.id === sessionId && item.scheduled_unread) || options.sessionIsUnreadLocally(sessionId)
  }

  function displaySessionTitle(session: Pick<SessionSummary, 'title'>) {
    return session.title || t('app.sidebar.new_chat')
  }

  /** Keep navigation labels compact without mutating the user-visible saved title. */
  function compactSessionTitle(session: Pick<SessionSummary, 'title'>, limit = 28) {
    const title = displaySessionTitle(session).trim()
    return title.length > limit ? `${title.slice(0, limit).trimEnd()}…` : title
  }

  function updateSessionTitleInLists(updated: SessionSummary) {
    sessions.value = sessions.value.map((item) => (item.id === updated.id ? { ...item, ...updated } : item))
    sessionSearchResults.value = sessionSearchResults.value.map((item) => (
      item.id === updated.id ? { ...item, ...updated } : item
    ))
  }

  function focusSessionTitleInput(sessionId: string) {
    nextTick(() => {
      const root = document.querySelector(`[data-session-title-input="${sessionId}"]`)
      const input = root?.querySelector('input') as HTMLInputElement | null
      input?.focus()
      input?.select()
    })
  }

  function startEditSessionTitle(session: SessionSummary | SessionSearchResult) {
    if (renamingSessionId.value) return
    editingSessionId.value = session.id
    editingSessionTitle.value = displaySessionTitle(session)
    focusSessionTitleInput(session.id)
  }

  function cancelSessionTitleEdit() {
    editingSessionId.value = null
    editingSessionTitle.value = ''
  }

  async function commitSessionTitleEdit(session: SessionSummary | SessionSearchResult) {
    const userId = getUserId()
    if (!userId || renamingSessionId.value === session.id) return
    const title = editingSessionTitle.value.trim()
    const previousTitle = displaySessionTitle(session)
    if (!title || title === previousTitle) {
      cancelSessionTitleEdit()
      return
    }
    renamingSessionId.value = session.id
    try {
      const updated = await updateSessionTitle(session.id, userId, getMainId(), title, authToken.value || null)
      updateSessionTitleInLists(updated)
      cancelSessionTitleEdit()
    } catch (error) {
      console.warn('[sessions] update title failed:', error)
      focusSessionTitleInput(session.id)
    } finally {
      renamingSessionId.value = null
    }
  }

  async function handleDeleteSession(sessionId: string) {
    const userId = getUserId()
    if (!userId || deletingSessionId.value === sessionId) return
    if (editingSessionId.value === sessionId) {
      cancelSessionTitleEdit()
    }
    const target =
      sessions.value.find((item) => item.id === sessionId) ||
      sessionSearchResults.value.find((item) => item.id === sessionId) ||
      null
    pendingDeleteSession.value = target
  }

  function cancelDeleteSession() {
    pendingDeleteSession.value = null
  }

  async function confirmDeleteSession() {
    const userId = getUserId()
    const sessionId = pendingDeleteSession.value?.id
    if (!userId || !sessionId || deletingSessionId.value === sessionId) return
    deletingSessionId.value = sessionId
    try {
      await deleteSession(sessionId, userId, getMainId(), authToken.value || null)
      sessions.value = sessions.value.filter((item) => item.id !== sessionId)
      sessionSearchResults.value = sessionSearchResults.value.filter((item) => item.id !== sessionId)
      options.removeSession(sessionId)
    } finally {
      pendingDeleteSession.value = null
      deletingSessionId.value = null
    }
  }

  async function loadSessions(reset = true) {
    const userId = getUserId()
    if (!userId) return
    const mainId = getMainId()
    const token = authToken.value
    if (reset) {
      sessionsLoading.value = true
      sessionsHasMore.value = false
    } else {
      sessionsLoadingMore.value = true
    }
    try {
      const page = await listSessionsPaged(userId, mainId, {
        limit: sessionPageSize,
        offset: reset ? 0 : sessions.value.length,
      }, token || null)
      if (token !== authToken.value || userId !== getUserId() || mainId !== getMainId()) return
      sessions.value = reset ? page.items : mergeSessionPages(sessions.value, page.items)
      sessionsHasMore.value = page.has_more
      if (canUseCode.value) void options.refreshWorkspaceTitles()
    } catch (error) {
      throw error
    } finally {
      if (token === authToken.value && userId === getUserId() && mainId === getMainId()) {
        if (reset) sessionsLoading.value = false
        else sessionsLoadingMore.value = false
      }
    }
  }

  async function refreshSessionSummaries() {
    const userId = getUserId()
    if (!userId || document.visibilityState === 'hidden') return
    const mainId = getMainId()
    const token = authToken.value
    try {
      const page = await listSessionsPaged(userId, mainId, {
        limit: Math.max(sessionPageSize, sessions.value.length), offset: 0,
      }, token || null)
      if (token !== authToken.value || userId !== getUserId() || mainId !== getMainId()) return
      sessions.value = mergeSessionPages(page.items, sessions.value).slice(0, Math.max(sessionPageSize, sessions.value.length))
      sessionsHasMore.value = page.has_more
      options.syncActiveRuns(page.items, userId)
    } catch {
      // Best-effort visibility refresh; explicit navigation still retries.
    }
  }

  // T26: "Shared with me" fetch — scope=shared via the client's scope param.
  // RESET-STYLE replace (NOT mergeSessionPages, which would retain a row the
  // viewer left); the window covers everything currently loaded so the section's
  // own pagination survives the poll. The server pins the activity order (todo 8)
  // — the response replaces the list as-is, no client re-sort by join order.
  async function loadSharedSessions(reset = true) {
    const userId = getUserId()
    if (!userId) return
    const mainId = getMainId()
    const token = authToken.value
    if (reset) {
      sharedSessionsLoading.value = true
      sharedSessionsHasMore.value = false
    } else {
      sharedSessionsLoadingMore.value = true
    }
    try {
      const page = await listSessionsPaged(userId, mainId, {
        limit: sessionPageSize,
        offset: reset ? 0 : sharedSessions.value.length,
        scope: 'shared',
      }, token || null)
      if (token !== authToken.value || userId !== getUserId() || mainId !== getMainId()) return
      sharedSessions.value = reset ? page.items : [...sharedSessions.value, ...page.items]
      sharedSessionsHasMore.value = page.has_more
    } catch (error) {
      if (reset) throw error
    } finally {
      if (token === authToken.value && userId === getUserId() && mainId === getMainId()) {
        if (reset) sharedSessionsLoading.value = false
        else sharedSessionsLoadingMore.value = false
      }
    }
  }

  async function refreshSharedSummaries() {
    const userId = getUserId()
    if (!userId || document.visibilityState === 'hidden') return
    const mainId = getMainId()
    const token = authToken.value
    try {
      const page = await listSessionsPaged(userId, mainId, {
        limit: Math.max(sessionPageSize, sharedSessions.value.length),
        offset: 0,
        scope: 'shared',
      }, token || null)
      if (token !== authToken.value || userId !== getUserId() || mainId !== getMainId()) return
      sharedSessions.value = page.items
      sharedSessionsHasMore.value = page.has_more
      options.syncActiveRuns(page.items, userId)
    } catch {
      // Best-effort visibility refresh; explicit navigation still retries.
    }
  }

  return {
    sessionIsRunning, sessionScheduledIsRunning, sessionNeedsHumanAssistance,
    sessionIsUnread, displaySessionTitle, compactSessionTitle,
    startEditSessionTitle, cancelSessionTitleEdit, commitSessionTitleEdit,
    handleDeleteSession, cancelDeleteSession, confirmDeleteSession,
    loadSessions, refreshSessionSummaries, loadSharedSessions,
    refreshSharedSummaries,
  }
}
