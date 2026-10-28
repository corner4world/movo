import { apiClient } from './client'

export interface SandboxStatus {
  enabled: boolean
  healthy: boolean
  running?: number
  pending?: number
  capacity?: number
  max_pending?: number
  plugin_runtimes?: number
  plugin_idle_seconds?: number
}

export async function fetchSandboxStatus(): Promise<SandboxStatus> {
  const { data } = await apiClient.get<SandboxStatus>('/api/settings/sandbox/status')
  return data
}

export async function saveSandboxQueueLimit(maxPending: number): Promise<void> {
  await apiClient.put('/api/settings/sandbox/settings', { max_pending: maxPending })
}
