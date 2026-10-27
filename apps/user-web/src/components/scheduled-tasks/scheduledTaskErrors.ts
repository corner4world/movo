import { getLocale, t } from '../../composables/i18n'
import { scheduledTaskErrorKeys } from '../../locales/legacyRecognitionValues'

export function scheduledTaskError(error: unknown, fallbackKey: string): string {
  const response = (error as { response?: { data?: { detail?: unknown } }; message?: unknown }) || {}
  const detail = response.response?.data?.detail
  const message = typeof detail === 'string' ? detail : response.message
  if (typeof message !== 'string' || !message) return t(fallbackKey)
  const key = scheduledTaskErrorKeys[message]
  if (key) return t(key)
  // Do not expose untranslated server errors in the English interface.
  if (getLocale() === 'en' && /[\u3400-\u9fff]/u.test(message)) return t(fallbackKey)
  return message
}
