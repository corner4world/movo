import { ref } from 'vue'
import type { SessionSearchResult, SessionSummary } from '../api/sessions'
import type { AppView } from './useAppNavigation'

/** Owner and shared sidebar lists keep independent paging and loading state. */
export function useAppSessionState() {
  const sessions = ref<SessionSummary[]>([])
  const sessionsLoading = ref(false)
  const sessionsLoadingMore = ref(false)
  const sessionsHasMore = ref(false)
  const sharedSessions = ref<SessionSummary[]>([])
  const sharedSessionsLoading = ref(false)
  const sharedSessionsLoadingMore = ref(false)
  const sharedSessionsHasMore = ref(false)
  const deletingSessionId = ref<string | null>(null)
  const pendingDeleteSession = ref<SessionSummary | SessionSearchResult | null>(null)
  const editingSessionId = ref<string | null>(null)
  const editingSessionTitle = ref('')
  const renamingSessionId = ref<string | null>(null)
  const currentView = ref<AppView>('chat')
  const scheduledTaskInitialPrompt = ref('')
  const scheduledTaskInitialSessionId = ref<string | null>(null)
  const scheduledTaskCreateRequestKey = ref(0)

  return {
    sessions, sessionsLoading, sessionsLoadingMore, sessionsHasMore,
    sharedSessions, sharedSessionsLoading, sharedSessionsLoadingMore,
    sharedSessionsHasMore, deletingSessionId, pendingDeleteSession,
    editingSessionId, editingSessionTitle, renamingSessionId, currentView,
    scheduledTaskInitialPrompt, scheduledTaskInitialSessionId, scheduledTaskCreateRequestKey,
  }
}
