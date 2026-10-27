import { t } from '../../../composables/i18n'
import { internalToolMessages } from '../../../locales/internalToolMessages'

export function localizedInternalToolLabel(name: unknown, fallback: unknown): string {
  const key = `internalTool.${String(name || '')}`
  if (key in internalToolMessages) return t(key)
  return String(fallback || name || '').trim()
}
