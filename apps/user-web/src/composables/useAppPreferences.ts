import { computed, ref, watch, type ComputedRef } from 'vue'
import { getSettings, updateSettings } from '../platform'
import { getBrowserTimezone, setAppTimezone } from './appTimezone'
import { setLocale, t, type Locale } from './i18n'

export type ThemeMode = 'light' | 'dark' | 'system'

const themeModeKey = 'askai.theme-mode'

export function useAppPreferences(locale: ComputedRef<Locale>) {
  const storedThemeMode = localStorage.getItem(themeModeKey)
  const themeMode = ref<ThemeMode>(
    storedThemeMode === 'light' || storedThemeMode === 'dark' || storedThemeMode === 'system'
      ? storedThemeMode
      : 'system',
  )
  const isDarkTheme = ref(false)
  const languageSaving = ref(false)
  const timezoneSaving = ref(false)
  const timezoneValue = ref(getBrowserTimezone())
  let systemThemeMedia: MediaQueryList | null = null

  const themeOptions = [
    { value: 'light' as const, langKey: 'ui.theme.light', icon: 'sun' },
    { value: 'dark' as const, langKey: 'ui.theme.dark', icon: 'moon' },
    { value: 'system' as const, langKey: 'ui.theme.system', icon: 'system' },
  ]
  const timezoneOptions = computed(() => [
    { label: t('app.timezone.shanghai'), value: 'Asia/Shanghai' },
    { label: t('app.timezone.tokyo'), value: 'Asia/Tokyo' },
    { label: t('app.timezone.utc'), value: 'UTC' },
    { label: t('app.timezone.berlin'), value: 'Europe/Berlin' },
    { label: t('app.timezone.london'), value: 'Europe/London' },
    { label: t('app.timezone.newYork'), value: 'America/New_York' },
    { label: t('app.timezone.chicago'), value: 'America/Chicago' },
    { label: t('app.timezone.losAngeles'), value: 'America/Los_Angeles' },
    { label: t('app.timezone.sydney'), value: 'Australia/Sydney' },
  ])

  function applyThemeMode() {
    const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    isDarkTheme.value = themeMode.value === 'dark' || (themeMode.value === 'system' && systemDark)
    document.documentElement.classList.toggle('theme-dark', isDarkTheme.value)
    document.documentElement.style.colorScheme = isDarkTheme.value ? 'dark' : 'light'
  }

  function handleSystemThemeChange() {
    if (themeMode.value === 'system') applyThemeMode()
  }

  function startThemeListener() {
    applyThemeMode()
    systemThemeMedia = window.matchMedia('(prefers-color-scheme: dark)')
    systemThemeMedia.addEventListener('change', handleSystemThemeChange)
  }

  function stopThemeListener() {
    systemThemeMedia?.removeEventListener('change', handleSystemThemeChange)
    systemThemeMedia = null
  }

  function selectThemeMode(mode: ThemeMode) {
    themeMode.value = mode
  }

  async function selectLanguage(language: Locale) {
    if (languageSaving.value || locale.value === language) return
    const previous = locale.value
    setLocale(language)
    languageSaving.value = true
    try {
      const settings = await getSettings()
      await updateSettings({ ...settings, language })
    } catch (error) {
      setLocale(previous)
      console.warn('[settings] failed to persist language', error)
    } finally {
      languageSaving.value = false
    }
  }

  async function selectTimezone(timezone: string) {
    if (timezoneSaving.value || timezoneValue.value === timezone) return
    const previous = timezoneValue.value
    timezoneValue.value = setAppTimezone(timezone)
    timezoneSaving.value = true
    try {
      const settings = await getSettings()
      await updateSettings({ ...settings, timezone })
    } catch (error) {
      timezoneValue.value = setAppTimezone(previous)
      console.warn('[settings] failed to persist timezone', error)
    } finally {
      timezoneSaving.value = false
    }
  }

  watch(themeMode, (value) => {
    localStorage.setItem(themeModeKey, value)
    applyThemeMode()
  })

  return {
    themeMode, isDarkTheme, themeOptions, languageSaving,
    timezoneSaving, timezoneValue, timezoneOptions,
    selectThemeMode, selectLanguage, selectTimezone,
    startThemeListener, stopThemeListener,
  }
}
