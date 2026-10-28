import { onBeforeUnmount, onMounted, watch, type Ref } from 'vue'
import type { UserProfile } from '../api/auth'
import { AUTH_EXPIRED_EVENT } from '../api/authExpiry'
import { capabilities, getSettings } from '../platform'
import { getBrowserTimezone, setAppTimezone } from './appTimezone'
import { restoreDesktopAuthToken } from './desktop/desktopAuthSession'
import { syncDesktopAgentIdentity } from './desktop/syncDesktopAgentIdentity'
import { setLocale, type Locale } from './i18n'
import { resolveViewFromPath, type AppView } from './useAppNavigation'

type StorageKeys = { token: string; account: string; users: string; profile: string }

type Options = {
  storageKeys: StorageKeys
  locale: Ref<Locale>
  currentView: Ref<AppView>
  desktopServerState: Ref<'checking' | 'required' | 'ready'>
  timezoneValue: Ref<string>
  currentAccount: Ref<string>
  authToken: Ref<string>
  userProfile: Ref<UserProfile | null>
  loginOpen: Ref<boolean>
  sessionsLoading: Ref<boolean>
  captureSessionShareToken: () => void
  captureSnapshotToken: () => void
  handleAuthExpired: () => void
  startThemeListener: () => void
  stopThemeListener: () => void
  loadSavedUsers: () => void
  loadUserProfile: () => void
  startLocalSession: (settings?: { shouldNavigate?: boolean }) => void
  refreshUserProfile: (token: string, createDefaultSession?: boolean, preserveSessionOnFailure?: boolean) => Promise<void>
  loadSessions: () => Promise<unknown>
  handleDocumentClick: (event: MouseEvent) => void
  handlePopState: (event: PopStateEvent) => void
  refreshSessionSummaries: () => Promise<unknown>
  refreshSharedSummaries: () => Promise<unknown>
}

/** Restores session state and binds the app-level lifecycle listeners. */
export function useAppStartup(options: Options) {
  let sessionRefreshTimer: ReturnType<typeof setInterval> | null = null

  function handleDesktopServerConnected() {
    for (const key of Object.values(options.storageKeys)) localStorage.removeItem(key)
    window.location.reload()
  }

  watch(options.locale, value => {
    document.documentElement.lang = value === 'en' ? 'en' : 'zh-CN'
  }, { immediate: true })

  onMounted(async () => {
    // Capture share tokens before navigation removes query parameters.
    options.captureSessionShareToken()
    options.captureSnapshotToken()
    window.addEventListener(AUTH_EXPIRED_EVENT, options.handleAuthExpired)
    options.startThemeListener()
    options.currentView.value = resolveViewFromPath(window.location.pathname)
    let serverConfigured = !capabilities.isDesktop
    let storedSettings = null
    try {
      storedSettings = await getSettings()
      serverConfigured = storedSettings.server_configured
      setLocale((storedSettings.language === 'en' ? 'en' : 'zh') as Locale)
      options.timezoneValue.value = setAppTimezone(storedSettings.timezone || getBrowserTimezone())
    } catch {
      setLocale('zh')
      options.timezoneValue.value = setAppTimezone(getBrowserTimezone())
    }
    if (capabilities.isDesktop && !serverConfigured) {
      options.desktopServerState.value = 'required'
      return
    }
    options.desktopServerState.value = 'ready'
    options.currentAccount.value = localStorage.getItem(options.storageKeys.account) || ''
    options.authToken.value = capabilities.isDesktop && storedSettings
      ? restoreDesktopAuthToken(storedSettings, localStorage, options.storageKeys.token)
      : localStorage.getItem(options.storageKeys.token) || ''
    options.loadSavedUsers()
    options.loadUserProfile()
    if (options.authToken.value && !options.userProfile.value) {
      options.startLocalSession({ shouldNavigate: options.currentView.value === 'chat' })
      options.sessionsLoading.value = true
      options.refreshUserProfile(options.authToken.value).catch(() => {
        options.sessionsLoading.value = false
      })
    } else if (options.authToken.value && options.userProfile.value) {
      options.startLocalSession({ shouldNavigate: options.currentView.value === 'chat' })
      options.refreshUserProfile(options.authToken.value, false, true).catch(() => {
        options.loadSessions().catch(() => {})
      })
    } else if (!options.authToken.value) {
      options.loginOpen.value = true
      options.startLocalSession({ shouldNavigate: options.currentView.value === 'chat' })
    }
    if (new URLSearchParams(window.location.search).has('invite_code')) options.loginOpen.value = true
    if (options.authToken.value && options.userProfile.value?.userId !== undefined) {
      void syncDesktopAgentIdentity(options.authToken.value, options.userProfile.value.userId)
    }
    document.addEventListener('click', options.handleDocumentClick)
    window.addEventListener('popstate', options.handlePopState)
    sessionRefreshTimer = setInterval(() => {
      void options.refreshSessionSummaries()
      void options.refreshSharedSummaries()
    }, 5000)
  })

  onBeforeUnmount(() => {
    if (sessionRefreshTimer) {
      clearInterval(sessionRefreshTimer)
      sessionRefreshTimer = null
    }
    document.removeEventListener('click', options.handleDocumentClick)
    window.removeEventListener('popstate', options.handlePopState)
    window.removeEventListener(AUTH_EXPIRED_EVENT, options.handleAuthExpired)
    options.stopThemeListener()
  })

  return { handleDesktopServerConnected }
}
