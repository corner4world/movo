import { ref, type Ref } from 'vue'
import type { UserProfile } from '../api/auth'

export function useStoredAccounts(options: {
  usersKey: string
  profileKey: string
  profile: Ref<UserProfile | null>
}) {
  const savedUsers = ref<string[]>([])

  function loadSavedUsers(): void {
    const raw = localStorage.getItem(options.usersKey)
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) {
        savedUsers.value = parsed.filter(item => typeof item === 'string')
      }
    } catch {
      savedUsers.value = []
    }
  }

  function persistSavedUsers(username: string): void {
    const next = [username, ...savedUsers.value.filter(item => item !== username)]
    savedUsers.value = next.slice(0, 5)
    localStorage.setItem(options.usersKey, JSON.stringify(savedUsers.value))
  }

  function loadUserProfile(): void {
    const raw = localStorage.getItem(options.profileKey)
    console.log('[auth] loadUserProfile raw:', raw)
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      console.log('[auth] loadUserProfile parsed:', parsed)
      if (parsed && typeof parsed === 'object') options.profile.value = parsed
    } catch (error) {
      console.warn('[auth] loadUserProfile parse failed:', error)
      options.profile.value = null
    }
  }

  return { savedUsers, loadSavedUsers, persistSavedUsers, loadUserProfile }
}
