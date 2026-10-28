import { nextTick, type Ref } from 'vue'
import { getAdminSSOToken, type TenantCandidate, type UserProfile } from '../api/auth'
import {
  activateEmbeddedBrowserSession, capabilities, openResource,
  selectEmbeddedBrowserSession,
} from '../platform'
import { t } from './i18n'
import { buildAdminSsoUrl } from '../utils/adminUrl'

type Options = {
  authToken: Ref<string>
  adminSsoStarting: Ref<boolean>
  availableTenants: Readonly<Ref<TenantCandidate[]>>
  userProfile: Ref<UserProfile | null>
  isEnterpriseSpace: Readonly<Ref<boolean>>
  canAccessAdmin: (tenant: TenantCandidate) => boolean
  isEnterpriseTenant: (tenant: Pick<TenantCandidate, 'spaceType' | 'orgName'>) => boolean
  getMainId: () => string
  switchToTenant: (mainId: string) => Promise<string | null>
  activeChatKey: Ref<string>
  currentSessionId: Ref<string | null>
  navigateToChat: () => void
  startLocalSession: () => void
  revealDesktopBrowser: () => void
  closeUserMenu: () => void
}

/** Opens an authorized admin session in a tab or the desktop browser surface. */
export function useAdminConsoleLaunch(options: Options) {
  async function openAdminConsole(mainId = options.getMainId()) {
    if (!options.authToken.value || options.adminSsoStarting.value) return
    const target = options.availableTenants.value.find(tenant => tenant.mainId === mainId)
    if (target && !options.canAccessAdmin(target)) return
    if (target && !options.isEnterpriseTenant(target)) return
    if (!target && options.userProfile.value?.canAccessAdmin !== true) return
    if (!target && !options.isEnterpriseSpace.value) return

    const adminWindow = capabilities.embeddedBrowser ? null : window.open('', '_blank')
    options.adminSsoStarting.value = true
    try {
      const token = await options.switchToTenant(mainId)
      if (!token) {
        adminWindow?.close()
        return
      }
      const result = await getAdminSSOToken(token)
      if (!result.ok || !result.ssoToken) {
        adminWindow?.close()
        window.alert(result.message || t('api.auth.auth_failed'))
        return
      }
      const adminUrl = buildAdminSsoUrl(result.ssoToken)
      if (capabilities.embeddedBrowser) {
        if (options.activeChatKey.value) options.navigateToChat()
        else options.startLocalSession()
        options.revealDesktopBrowser()
        const browserSessionId = options.currentSessionId.value || options.activeChatKey.value
        if (browserSessionId) {
          await selectEmbeddedBrowserSession(browserSessionId)
          await activateEmbeddedBrowserSession(browserSessionId)
        }
        await nextTick()
        await new Promise<void>(resolve => window.requestAnimationFrame(() => resolve()))
        await openResource(adminUrl, 'internal')
      } else if (adminWindow) {
        adminWindow.location.href = adminUrl
      } else {
        window.open(adminUrl, '_blank')
      }
      options.closeUserMenu()
    } catch (error: any) {
      adminWindow?.close()
      window.alert(error?.message || t('api.auth.auth_failed'))
    } finally {
      options.adminSsoStarting.value = false
    }
  }

  return { openAdminConsole }
}
