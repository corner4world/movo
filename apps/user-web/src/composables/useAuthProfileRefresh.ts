import type { Ref } from 'vue'
import { fetchUserProfile, type UserProfile } from '../api/auth'
import type { AppView } from './useAppNavigation'
import { useProfileRefreshOnResume } from './useProfileRefreshOnResume'
import { syncDesktopAgentIdentity } from './desktop/syncDesktopAgentIdentity'

export function useAuthProfileRefresh(options: {
  token: Ref<string>
  profile: Ref<UserProfile | null>
  loginOpen: Ref<boolean>
  sessionsLoading: Ref<boolean>
  currentView: Ref<AppView>
  tokenStorageKey: string
  profileStorageKey: string
  startLocalSession: () => void
  loadSessions: () => Promise<unknown>
  loadSharedSessions: () => Promise<unknown>
  joinPendingSharedSession: () => Promise<void>
  prepareProjectBoundary: (profile: UserProfile) => boolean
  onAuthExpired: () => void
  refreshWorkspaceTitles: () => Promise<unknown>
  loadSkills: () => Promise<unknown>
}) {
  async function refreshUserProfile(
    token: string,
    createDefaultSession = false,
    preserveSessionOnFailure = false,
  ): Promise<void> {
    if (createDefaultSession) options.startLocalSession()
    const result = await fetchUserProfile(token)
    if (options.token.value !== token) return
    if (result.status === 401) {
      if (options.token.value === token) options.onAuthExpired()
      return
    }
    if (result.ok && result.data) {
      options.prepareProjectBoundary(result.data)
      options.profile.value = result.data
      localStorage.setItem(options.profileStorageKey, JSON.stringify(result.data))
      await options.loadSessions().catch(() => {})
      void options.loadSharedSessions().catch(() => {})
      if (!new URLSearchParams(window.location.search).has('invite_code')) options.loginOpen.value = false
      void options.joinPendingSharedSession().catch(() => {})
      void syncDesktopAgentIdentity(token, result.data.userId)
      return
    }
    if (preserveSessionOnFailure) {
      options.sessionsLoading.value = false
      console.warn('[auth] fetchUserProfile failed; keeping cached session and retrying later')
      await options.loadSessions().catch(() => {})
      void options.loadSharedSessions().catch(() => {})
      return
    }
    options.sessionsLoading.value = false
    console.warn('[auth] fetchUserProfile failed; opening login dialog for fresh sign-in')
    localStorage.removeItem(options.tokenStorageKey)
    localStorage.removeItem(options.profileStorageKey)
    options.token.value = ''
    options.profile.value = null
    options.loginOpen.value = true
  }

  async function refreshEnterprisePolicy(token: string): Promise<void> {
    const result = await fetchUserProfile(token)
    if (result.status === 401) {
      if (options.token.value === token) options.onAuthExpired()
      return
    }
    if (!result.ok || !result.data || options.token.value !== token) return
    const nextCodeAllowed = options.prepareProjectBoundary(result.data)
    options.profile.value = result.data
    localStorage.setItem(options.profileStorageKey, JSON.stringify(result.data))
    if (nextCodeAllowed) await options.refreshWorkspaceTitles()
    if (options.currentView.value === 'skills') await options.loadSkills().catch(() => {})
  }

  useProfileRefreshOnResume({ token: options.token, refresh: refreshEnterprisePolicy })
  return { refreshUserProfile, refreshEnterprisePolicy }
}
