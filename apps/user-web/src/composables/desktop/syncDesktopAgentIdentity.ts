import { capabilities, getAgentStatus, getSettings, startAgent, updateSettings } from '../../platform'

// The local agent reads credentials when it starts. Keep its persisted
// identity aligned with the authenticated account after login or tenant switch.
export async function syncDesktopAgentIdentity(
  token: string,
  userId: string | number | null | undefined,
): Promise<boolean> {
  if (!capabilities.isDesktop) return true
  const uid = userId !== undefined && userId !== null ? String(userId) : ''
  if (!uid || !token) return false
  try {
    const [current, status] = await Promise.all([getSettings(), getAgentStatus()])
    const settingsMatch = current.user_id === uid && current.auth_token === token
    if (settingsMatch && status.running) return true
    if (!settingsMatch) {
      await updateSettings({ ...current, user_id: uid, auth_token: token })
      if (!status.running) await startAgent()
      return true
    }
    if (!status.running) await startAgent()
    return true
  } catch (error) {
    console.warn('[desktop] failed to sync agent identity', error)
    return false
  }
}
