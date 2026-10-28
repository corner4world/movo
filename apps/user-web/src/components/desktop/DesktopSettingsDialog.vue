<script setup lang="ts">
import SettingsPanel from '../SettingsPanel.vue'
import { t } from '../../composables/i18n'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <div
    v-if="open"
    class="desktop-settings-modal fixed inset-0 z-[80] flex items-start justify-center bg-slate-900/30 px-4 pb-4 pt-16 backdrop-blur-[2px]"
    @click.self="emit('close')"
  >
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="desktop-settings-title"
      class="flex max-h-[calc(100vh-80px)] w-full max-w-2xl flex-col overflow-hidden rounded-[28px] border border-gray-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.18)]"
    >
      <div class="flex shrink-0 items-center justify-between border-b border-gray-100 py-2 pl-6 pr-3">
        <div id="desktop-settings-title" class="text-lg font-semibold text-gray-900">{{ t('settings.modal.title') }}</div>
        <button
          type="button"
          class="flex min-h-11 min-w-11 items-center justify-center rounded-xl px-3 text-sm text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          @click="emit('close')"
        >
          {{ t('ui.close') }}
        </button>
      </div>
      <div class="min-h-0 overflow-y-auto overscroll-contain">
        <SettingsPanel />
      </div>
    </div>
  </div>
</template>
