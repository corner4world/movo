import { computed, ref } from 'vue'
import type { TenantCandidate, UserProfile } from '../api/auth'
import { personalSpaceName } from '../locales/legacyIdentityValues'
import { capabilities } from '../platform'
import { useStoredAccounts } from './useStoredAccounts'

/** Account identity, dialog visibility, and persisted account keys. */
export function useAppAuthState() {
  const storageKeys = {
    token: 'auth_token', account: 'auth_account',
    users: 'auth_users', profile: 'auth_user_profile',
  } as const
  const loginOpen = ref(false)
  const billingOpen = ref(false)
  const profileOpen = ref(false)
  const createOrganizationOpen = ref(false)
  const authToken = ref('')
  const currentAccount = ref('')
  const userProfile = ref<UserProfile | null>(null)
  const { savedUsers, loadSavedUsers, persistSavedUsers, loadUserProfile } = useStoredAccounts({
    usersKey: storageKeys.users, profileKey: storageKeys.profile, profile: userProfile,
  })
  const userMenuOpen = ref(false)
  const adminSsoStarting = ref(false)
  const billingSummary = ref<any>(null)
  const billingSummaryLoading = ref(false)
  const billingSummaryLoaded = ref(false)
  const settingsPanelOpen = ref(false)
  const desktopServerState = ref<'checking' | 'required' | 'ready'>(capabilities.isDesktop ? 'checking' : 'ready')
  const personalizationOpen = ref(false)
  const isLoggedIn = computed(() => Boolean(authToken.value))
  const availableTenants = computed<TenantCandidate[]>(() => userProfile.value?.availableTenants || [])

  function getUserId() {
    const id = userProfile.value?.userId
    if (id === undefined || id === null) return null
    return String(id)
  }

  function getMainId() {
    return String(userProfile.value?.mainId || 'default')
  }

  function isEnterpriseTenant(tenant: Pick<TenantCandidate, 'spaceType' | 'orgName'>) {
    if (tenant.spaceType) return tenant.spaceType === 'enterprise'
    return String(tenant.orgName || '').trim() !== personalSpaceName
  }

  return {
    storageKeys, loginOpen, billingOpen, profileOpen, createOrganizationOpen,
    authToken, currentAccount, userProfile, savedUsers, loadSavedUsers,
    persistSavedUsers, loadUserProfile, userMenuOpen, adminSsoStarting,
    billingSummary, billingSummaryLoading, billingSummaryLoaded,
    settingsPanelOpen, desktopServerState, personalizationOpen,
    isLoggedIn, availableTenants, getUserId, getMainId, isEnterpriseTenant,
  }
}
