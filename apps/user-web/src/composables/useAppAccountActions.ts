import type { Ref } from 'vue'
import type { UserProfile } from '../api/auth'
import { capabilities } from '../platform'

type AccountActionOptions = {
  isLoggedIn: Readonly<Ref<boolean>>
  canCreateOrganization: Readonly<Ref<boolean>>
  canUpgradePlan: Readonly<Ref<boolean>>
  loginOpen: Ref<boolean>
  profileOpen: Ref<boolean>
  createOrganizationOpen: Ref<boolean>
  billingOpen: Ref<boolean>
  personalizationOpen: Ref<boolean>
  userMenuOpen: Ref<boolean>
  settingsPanelOpen: Ref<boolean>
  userProfile: Ref<UserProfile | null>
  currentAccount: Ref<string>
  profileStorageKey: string
  accountStorageKey: string
  prepareProjectBoundary: (profile: UserProfile) => boolean
  loadBillingSummary: () => Promise<void>
}

/** Owns account-menu visibility and profile updates across web and desktop. */
export function useAppAccountActions(options: AccountActionOptions) {
  const {
    isLoggedIn, canCreateOrganization, canUpgradePlan, loginOpen,
    profileOpen, createOrganizationOpen, billingOpen, personalizationOpen,
    userMenuOpen, settingsPanelOpen, userProfile, currentAccount,
    profileStorageKey, accountStorageKey, prepareProjectBoundary, loadBillingSummary,
  } = options

  function openLogin() {
    loginOpen.value = true
  }

  function closeUserMenu() {
    userMenuOpen.value = false
  }

  function openProfileEditor() {
    profileOpen.value = true
    closeUserMenu()
  }

  function openCreateOrganization() {
    if (!canCreateOrganization.value) return
    createOrganizationOpen.value = true
    closeUserMenu()
  }

  function openBilling() {
    if (!canUpgradePlan.value) return
    billingOpen.value = true
    closeUserMenu()
  }

  function openPersonalization() {
    personalizationOpen.value = true
    closeUserMenu()
  }

  function closePersonalization() {
    personalizationOpen.value = false
  }

  function handleProfileUpdated(profile: UserProfile) {
    prepareProjectBoundary(profile)
    userProfile.value = profile
    localStorage.setItem(profileStorageKey, JSON.stringify(profile))
    if (profile.username) {
      currentAccount.value = profile.username
      localStorage.setItem(accountStorageKey, profile.username)
    }
  }

  function toggleUserMenu() {
    if (!isLoggedIn.value) {
      openLogin()
      return
    }
    userMenuOpen.value = !userMenuOpen.value
    if (userMenuOpen.value) void loadBillingSummary()
  }

  function openSettingsPanel() {
    if (!capabilities.isDesktop) return
    settingsPanelOpen.value = true
    closeUserMenu()
  }

  function closeSettingsPanel() {
    settingsPanelOpen.value = false
  }

  function handleDocumentClick(event: MouseEvent) {
    const target = event.target as HTMLElement | null
    if (!target?.closest('[data-user-menu]')) closeUserMenu()
  }

  return {
    openLogin, closeUserMenu, openProfileEditor, openCreateOrganization,
    openBilling, openPersonalization, closePersonalization,
    handleProfileUpdated, toggleUserMenu, openSettingsPanel,
    closeSettingsPanel, handleDocumentClick,
  }
}
