import { getLocale, t, translateSourceText } from '../composables/i18n'

export function workflowResponseText(value: unknown, fallbackKey: string): string {
  if (typeof value !== 'string' || !value) return t(fallbackKey)
  const translated = translateSourceText(value)
  return getLocale() === 'en' && /[\u3400-\u9fff]/u.test(translated) ? t(fallbackKey) : translated
}
