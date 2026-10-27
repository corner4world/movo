import { codeRuntimeErrorMessages } from '../../locales/codeRuntimeErrorMessages'

export function codeRuntimeErrorMessage(error: unknown, locale: 'zh' | 'en'): string {
  const raw = String(error instanceof Error ? error.message : error || '')
  const normalized = raw.toLowerCase()
  if (normalized.includes('code permission setting') || normalized.includes('code permission config') ||
      normalized.includes('automatic review requires')) {
    return codeRuntimeErrorMessages.permissions[locale]
  }
  if (normalized.includes('already owned by an active write handle')) {
    return codeRuntimeErrorMessages.restoring[locale]
  }
  if (normalized.includes('another desktop device')) {
    return codeRuntimeErrorMessages.otherDevice[locale]
  }
  if (normalized.includes('workspace') && (normalized.includes('unavailable') || normalized.includes('missing'))) {
    return codeRuntimeErrorMessages.missingFolder[locale]
  }
  if (normalized.includes('profile') && (normalized.includes('compatible') || normalized.includes('changed'))) {
    return codeRuntimeErrorMessages.incompatibleProfile[locale]
  }
  if (normalized.includes('runtime') && (normalized.includes('unavailable') || normalized.includes('ready'))) {
    return codeRuntimeErrorMessages.runtimeUnavailable[locale]
  }
  return raw || codeRuntimeErrorMessages.taskUnavailable[locale]
}
