import type { Ref } from 'vue'
import type { UserProfile } from '../api/auth'
import type { SessionSummary } from '../api/sessions'
import { syncDesktopAgentIdentity } from './desktop/syncDesktopAgentIdentity'

type LoginPayload = { token: string; username: string; profile?: UserProfile }

export function useAuthLogin(options: {
  sessions: Ref<SessionSummary[]>
  sharedSessions: Ref<SessionSummary[]>
  sessionsHasMore: Ref<boolean>
  sharedSessionsHasMore: Ref<boolean>
  token: Ref<string>
  account: Ref<string>
  profile: Ref<UserProfile | null>
  loginOpen: Ref<boolean>
  billingSummary: Ref<any>
  billingSummaryLoaded: Ref<boolean>
  tokenStorageKey: string
  accountStorageKey: string
  profileStorageKey: string
  resetChat: () => void
  clearProjectState: () => void
  persistSavedUser: (username: string) => void
  startLocalSession: () => void
  loadSessions: () => Promise<unknown>
  loadSharedSessions: () => Promise<unknown>
  joinPendingSharedSession: () => Promise<void>
  refreshUserProfile: (token: string, createDefaultSession: boolean) => Promise<void>
  canUseCode: Ref<boolean>
  refreshWorkspaceTitles: () => Promise<unknown>
}) {
  function handleLoginSuccess(payload: LoginPayload): void {
    options.sessions.value = []
    options.sharedSessions.value = []
    options.sessionsHasMore.value = false
    options.sharedSessionsHasMore.value = false
    options.resetChat()
    options.profile.value = null
    localStorage.removeItem(options.profileStorageKey)
    options.token.value = payload.token
    options.account.value = payload.username
    options.loginOpen.value = false
    options.clearProjectState()
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href)
      if (['invite_code', 'inviteCode', 'register'].some(key => url.searchParams.has(key))) {
        for (const key of ['invite_code', 'inviteCode', 'register', 'invite', 'username', 'loginName']) {
          url.searchParams.delete(key)
        }
        window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
      }
    }
    try {
      localStorage.setItem(options.tokenStorageKey, payload.token)
      localStorage.setItem(options.accountStorageKey, payload.username)
    } catch (error) {
      console.warn('[auth] failed to persist login credentials', error)
    }
    options.billingSummary.value = null
    options.billingSummaryLoaded.value = false
    try {
      options.persistSavedUser(payload.username)
    } catch (error) {
      console.warn('[auth] failed to persist login history', error)
    }
    if (payload.profile && payload.profile.userId !== undefined && payload.profile.userId !== null) {
      options.profile.value = payload.profile
      try {
        localStorage.setItem(options.profileStorageKey, JSON.stringify(payload.profile))
      } catch (error) {
        console.warn('[auth] failed to persist user profile', error)
      }
      options.startLocalSession()
      options.loadSessions().catch(() => {})
      void options.loadSharedSessions().catch(() => {})
      void options.joinPendingSharedSession().catch(() => {})
      void syncDesktopAgentIdentity(payload.token, payload.profile.userId).then(() => {
        if (options.canUseCode.value) void options.refreshWorkspaceTitles()
      })
    } else {
      void options.refreshUserProfile(payload.token, true)
    }
  }

  return { handleLoginSuccess }
}
