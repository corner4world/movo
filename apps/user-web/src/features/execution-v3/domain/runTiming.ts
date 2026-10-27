import type { ExecutionEventV3 } from './protocol'
import { durationMessages } from '../../../locales/codePresentationMessages'

export const TERMINAL_RUN_EVENT_TYPES = new Set<ExecutionEventV3['type']>([
  'run.completed',
  'run.failed',
  'run.cancelled',
  'run.blocked',
])

export function elapsedRunMs(startedAt: number | null, endedAt: number | null, now: number): number | null {
  if (!startedAt) return null
  return Math.max(0, (endedAt || now) - startedAt)
}

export function formatRunDuration(durationMs: number | null, locale: 'zh' | 'en'): string {
  if (durationMs === null) return ''
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  const values = { hours, minutes, seconds }
  const key = hours ? 'hours' : minutes ? 'minutes' : 'seconds'
  return durationMessages[key][locale].replace(/\{(\w+)\}/g, (_, name: string) => String(values[name as keyof typeof values]))
}
