<script setup lang="ts">
import { ref, watch } from 'vue'
import { NSelect } from 'naive-ui'
import { AppsOutline, SettingsOutline } from '@vicons/ionicons5'
import ShortcutPreferencesPanel from './settings/ShortcutPreferencesPanel.vue'
import { t, type Locale } from '../composables/i18n'
import { appLanguageOptions } from '../locales/legacyIdentityValues'
import type { ThemeMode } from '../composables/useAppPreferences'

const props = defineProps<{
  open: boolean
  locale: Locale
  languageSaving: boolean
  timezoneValue: string
  timezoneOptions: { label: string; value: string }[]
  timezoneSaving: boolean
  themeMode: ThemeMode
  themeOptions: { value: ThemeMode; langKey: string; icon: string }[]
  userId: string | null
  mainId: string
}>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'select-language', language: Locale): void
  (e: 'select-timezone', timezone: string): void
  (e: 'select-theme', mode: ThemeMode): void
}>()
const section = ref<'general' | 'shortcuts'>('general')
const languageOptions = appLanguageOptions
watch(() => props.open, (open) => {
  if (open) section.value = 'general'
})
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-[90] flex items-center justify-center bg-slate-900/30 px-4 backdrop-blur-[2px]"
    @click.self="emit('close')"
  >
    <div class="max-h-[calc(100vh-48px)] w-full max-w-3xl overflow-y-auto rounded-2xl border border-gray-200 bg-white p-5 shadow-[0_24px_80px_rgba(15,23,42,0.18)]">
      <div class="mb-5 flex items-start justify-between gap-4">
        <div>
          <div class="text-lg font-semibold text-gray-900">{{ t('app.account.personalization') }}</div>
          <div class="mt-1 text-sm text-gray-500">{{ t('ui.personalization_desc') }}</div>
        </div>
        <button
          type="button"
          class="flex h-9 w-9 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
          :aria-label="t('ui.close')"
          @click="emit('close')"
        >
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M18 6 6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <div class="personalization-layout">
        <nav class="personalization-nav" :aria-label="t('shortcuts.personalization_menu')">
          <button type="button" class="personalization-nav-item" :class="{ active: section === 'general' }" :aria-current="section === 'general' ? 'page' : undefined" @click="section = 'general'">
            <SettingsOutline class="personalization-nav-icon" aria-hidden="true" />
            <span>{{ t('shortcuts.general_settings') }}</span>
          </button>
          <button type="button" class="personalization-nav-item" :class="{ active: section === 'shortcuts' }" :aria-current="section === 'shortcuts' ? 'page' : undefined" @click="section = 'shortcuts'">
            <AppsOutline class="personalization-nav-icon" aria-hidden="true" />
            <span>{{ t('shortcuts.title') }}</span>
          </button>
        </nav>

        <main class="personalization-content">
      <div v-show="section === 'general'">
      <div class="mb-5">
        <div class="mb-2 text-sm font-medium text-gray-700">{{ t('settings.language') }}</div>
        <div class="grid grid-cols-2 gap-3">
          <button
            v-for="option in languageOptions"
            :key="option.value"
            type="button"
            class="min-h-[44px] rounded-xl border px-4 text-sm font-medium transition-colors disabled:cursor-wait disabled:opacity-60"
            :class="locale === option.value
              ? 'border-blue-500 bg-blue-50 text-blue-700 ring-2 ring-blue-100'
              : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50'"
            :aria-pressed="locale === option.value"
            :disabled="languageSaving"
            @click="emit('select-language', option.value)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>

      <div class="mb-5">
        <div class="mb-2 text-sm font-medium text-gray-700">{{ t('settings.timezone') }}</div>
        <n-select
          :value="timezoneValue"
          :options="timezoneOptions"
          filterable
          :disabled="timezoneSaving"
          @update:value="value => emit('select-timezone', value)"
        />
      </div>

      <div class="mb-2 text-sm font-medium text-gray-700">{{ t('ui.appearance') }}</div>
      <div class="grid grid-cols-3 gap-3">
        <button
          v-for="option in themeOptions"
          :key="option.value"
          type="button"
          class="flex min-h-[116px] flex-col items-center justify-center gap-3 rounded-xl border px-2 text-sm font-medium transition-colors"
          :class="themeMode === option.value
            ? 'border-blue-500 bg-blue-50 text-blue-700 ring-2 ring-blue-100'
            : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50'"
          :aria-pressed="themeMode === option.value"
          @click="emit('select-theme', option.value)"
        >
          <span class="flex h-10 w-10 items-center justify-center rounded-full bg-current/10">
            <svg v-if="option.icon === 'sun'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="12" cy="12" r="4"/>
              <path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"/>
            </svg>
            <svg v-else-if="option.icon === 'moon'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z"/>
            </svg>
            <svg v-else class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <rect x="3" y="4" width="18" height="13" rx="2"/>
              <path d="M8 21h8M12 17v4"/>
            </svg>
          </span>
          <span>{{ t(option.langKey) }}</span>
        </button>
      </div>
      </div>
      <div v-if="section === 'shortcuts'" class="mt-5">
        <ShortcutPreferencesPanel :user-id="userId" :main-id="mainId" />
      </div>
        </main>
      </div>
    </div>
  </div>
</template>
