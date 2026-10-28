import { ref, type Ref } from 'vue'
import { switchTenant, type UserProfile } from '../api/auth'

export function useTenantSwitch(options: {
  token: Ref<string>
  profile: Ref<UserProfile | null>
  account: Ref<string>
  billingSummary: Ref<any>
  billingSummaryLoaded: Ref<boolean>
  tokenStorageKey: string
  profileStorageKey: string
  accountStorageKey: string
  getMainId: () => string
  clearProjectState: () => void
  loadBillingSummary: () => Promise<unknown>
  startLocalSession: () => void
  loadSessions: () => Promise<unknown>
  loadSharedSessions: () => Promise<unknown>
}) {
  const switchingTenant = ref(false)

  async function switchToTenant(mainId: string): Promise<string | null> {
    const target = String(mainId || '').trim()
    if (!target || !options.token.value || switchingTenant.value) return null
    if (target === options.getMainId()) return options.token.value
    switchingTenant.value = true
    try {
      const result = await switchTenant(options.token.value, target)
      if (!result.ok || !result.token) return null
      options.clearProjectState()
      localStorage.setItem(options.tokenStorageKey, result.token)
      options.token.value = result.token
      if (result.profile) {
        options.profile.value = result.profile
        localStorage.setItem(options.profileStorageKey, JSON.stringify(result.profile))
        if (result.profile.username) {
          options.account.value = result.profile.username
          localStorage.setItem(options.accountStorageKey, result.profile.username)
        }
      }
      options.billingSummary.value = null
      options.billingSummaryLoaded.value = false
      void options.loadBillingSummary()
      options.startLocalSession()
      await options.loadSessions()
      void options.loadSharedSessions().catch(() => {})
      return result.token
    } finally {
      switchingTenant.value = false
    }
  }

  async function handleSwitchTenant(mainId: string): Promise<void> {
    await switchToTenant(mainId)
  }

  return { switchingTenant, switchToTenant, handleSwitchTenant }
}
