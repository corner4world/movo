import type { Ref } from 'vue'
import { logoutWithToken, type UserProfile } from '../api/auth'
import type { SessionSummary } from '../api/sessions'
import { capabilities, getAgentStatus, getSettings, stopAgent, updateSettings } from '../platform'
import { clearDesktopAuthSession } from './desktop/desktopAuthSession'

export function useAuthSessionLifecycle(options: {
  token: Ref<string>
  account: Ref<string>
  profile: Ref<UserProfile | null>
  billingSummary: Ref<any>
  billingSummaryLoaded: Ref<boolean>
  userMenuOpen: Ref<boolean>
  loginOpen: Ref<boolean>
  sessions: Ref<SessionSummary[]>
  sharedSessions: Ref<SessionSummary[]>
  sessionsHasMore: Ref<boolean>
  sharedSessionsHasMore: Ref<boolean>
  sessionsLoading: Ref<boolean>
  sessionsLoadingMore: Ref<boolean>
  sharedSessionsLoading: Ref<boolean>
  sharedSessionsLoadingMore: Ref<boolean>
  createProjectOpen: Ref<boolean>
  createProjectSelectionError: Ref<string>
  tokenStorageKey: string
  accountStorageKey: string
  profileStorageKey: string
  clearProjectState: () => void
  resetChat: () => void
  closeSessionSearch: () => void
}) {
  function clearAuthenticatedState(): void {
    options.clearProjectState()
    localStorage.removeItem(options.tokenStorageKey)
    localStorage.removeItem(options.accountStorageKey)
    localStorage.removeItem(options.profileStorageKey)
    options.token.value = ''
    options.account.value = ''
    options.profile.value = null
    options.billingSummary.value = null
    options.billingSummaryLoaded.value = false
    options.userMenuOpen.value = false
    options.sessions.value = []
    options.sharedSessions.value = []
    options.sessionsHasMore.value = false
    options.sharedSessionsHasMore.value = false
    options.sessionsLoading.value = false
    options.sessionsLoadingMore.value = false
    options.sharedSessionsLoading.value = false
    options.sharedSessionsLoadingMore.value = false
    options.resetChat()
    options.closeSessionSearch()
    if (capabilities.isDesktop) {
      void clearDesktopAuthSession({ getSettings, updateSettings, getAgentStatus, stopAgent }).catch(error => {
        console.warn('[desktop] failed to clear persisted authentication', error)
      })
    }
  }

  function logout(): void {
    if (options.token.value) void logoutWithToken(options.token.value)
    clearAuthenticatedState()
  }

  function handleAuthExpired(): void {
    if (!options.token.value && !localStorage.getItem(options.tokenStorageKey)) return
    console.warn('[auth] session expired; clearing cached session and opening login dialog')
    options.createProjectOpen.value = false
    options.createProjectSelectionError.value = ''
    clearAuthenticatedState()
    options.loginOpen.value = true
  }

  return { clearAuthenticatedState, logout, handleAuthExpired }
}
