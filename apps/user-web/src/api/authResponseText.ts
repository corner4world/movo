import { getLocale, t, translateSourceText } from '../composables/i18n'

export function authResponseText(value: unknown, fallbackKey?: string): string | undefined {
  if (typeof value !== 'string' || !value) return fallbackKey ? t(fallbackKey) : undefined
  const localized = translateSourceText(value)
  if (getLocale() === 'en' && /[\u3400-\u9fff]/u.test(localized)) {
    return fallbackKey ? t(fallbackKey) : t('api.auth.auth_failed')
  }
  return localized
}
