<script setup lang="ts">
import type { SessionSearchResult, SessionSummary } from '../../api/sessions'
import { t } from '../../composables/i18n'

defineProps<{
  session: SessionSummary | SessionSearchResult | null
  deletingSessionId: string | null
}>()
const emit = defineEmits<{ cancel: []; confirm: [] }>()
</script>

<template>
  <div
    v-if="session"
    class="fixed inset-0 z-[70] flex items-center justify-center bg-slate-900/22 px-4 backdrop-blur-[2px]"
    @click.self="emit('cancel')"
  >
    <div class="w-full max-w-md rounded-[24px] border border-gray-200 bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.18)]">
      <div class="text-lg font-semibold text-gray-900">{{ t('app.delete_chat.title') }}</div>
      <div class="mt-3 text-sm leading-6 text-gray-500">
        {{ t('app.delete_chat.body', { title: session.title || t('app.sidebar.new_chat') }) }}
      </div>
      <div class="mt-6 flex items-center justify-end gap-3">
        <button
          type="button"
          class="rounded-xl px-4 py-2.5 text-sm font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700"
          @click="emit('cancel')"
        >
          {{ t('ui.cancel') }}
        </button>
        <button
          type="button"
          class="rounded-xl bg-red-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="deletingSessionId === session.id"
          @click="emit('confirm')"
        >
          {{ deletingSessionId === session.id ? t('app.delete_chat.deleting') : t('ui.delete') }}
        </button>
      </div>
    </div>
  </div>
</template>
