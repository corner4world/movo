import type { Ref } from 'vue'
import type { UserProfile } from '../api/auth'
import { fetchUserProfile } from '../api/auth'
import { t } from './i18n'

type AccountIdentityOptions = {
  profile: Ref<UserProfile | null>
  account: Ref<string>
  token: Ref<string>
  profileStorageKey: string
}

export function useAccountIdentity(options: AccountIdentityOptions) {
  function normalizedPhone(): string {
    const value = String(options.profile.value?.phone || options.profile.value?.username || options.account.value || '').replace(/\D/g, '')
    return /^1[3-9]\d{9}$/.test(value) ? value : ''
  }

  function maskedPhone(): string {
    const phone = normalizedPhone()
    return phone ? `${phone.slice(0, 3)}****${phone.slice(-4)}` : ''
  }

  function displayName(): string {
    const profileName = String(options.profile.value?.name || '').trim()
    const phone = normalizedPhone()
    if (profileName && profileName !== phone && !/^1[3-9]\d{9}$/.test(profileName)) return profileName
    if (phone) return t('app.userWithPhone', { phone: phone.slice(-4) })
    return options.account.value || t('app.sidebar.login_register')
  }

  function displayAvatar(): string {
    const avatar = options.profile.value?.avatar || ''
    return avatar && avatar !== 'null' ? avatar : ''
  }

  function displayAvatarText(): string {
    return normalizedPhone() ? t('app.userInitial') : displayName().slice(0, 1)
  }

  function handleAvatarError(event: Event): void {
    const image = event.currentTarget as HTMLImageElement
    const retryCount = Number(image.dataset.retryCount || 0)
    if (retryCount >= 5 || !options.token.value) {
      image.style.display = 'none'
      return
    }
    image.dataset.retryCount = String(retryCount + 1)
    const retryDelay = [1000, 2000, 4000, 8000, 15000][retryCount] || 15000
    window.setTimeout(async () => {
      const result = await fetchUserProfile(options.token.value)
      if (!result.ok || !result.data?.avatar) return
      options.profile.value = result.data
      localStorage.setItem(options.profileStorageKey, JSON.stringify(result.data))
      const avatar = result.data.avatar
      image.src = avatar.startsWith('/')
        ? `${avatar}${avatar.includes('?') ? '&' : '?'}retry=${Date.now()}`
        : avatar
    }, retryDelay)
  }

  return { maskedPhone, displayName, displayAvatar, displayAvatarText, handleAvatarError }
}
