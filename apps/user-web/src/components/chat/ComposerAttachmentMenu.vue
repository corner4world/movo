<script setup lang="ts">
import { ref } from 'vue'
import { t } from '../../composables/i18n'

defineProps<{
  open: boolean
  running: boolean
  blocked?: boolean
  allowKnowledge?: boolean
  knowledgeQaEnabled: boolean
  knowledgeLabel: string
}>()
const emit = defineEmits<{
  (e: 'toggle'): void
  (e: 'image'): void
  (e: 'document'): void
  (e: 'knowledge'): void
}>()
const root = ref<HTMLElement | null>(null)
defineExpose({ root })
</script>

<template>
        <div ref="root" class="relative">
          <button
            class="flex h-7 w-7 items-center justify-center rounded-md text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-100"
            :disabled="running || blocked"
            :aria-label="t('composer.addAttachment')"
            @click.stop="emit('toggle')"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
          </button>
          <div
            v-if="open"
            class="absolute bottom-9 left-0 min-w-[220px] overflow-hidden rounded-xl border border-gray-200 bg-white py-1 shadow-lg"
          >
            <button
              class="flex w-full items-center gap-2 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
              @click="emit('image')"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <circle cx="8.5" cy="8.5" r="1.5"></circle>
                <polyline points="21 15 16 10 5 21"></polyline>
              </svg>
              {{ t('chat.upload_image') }}
            </button>
            <button
              class="flex w-full items-center gap-2 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
              @click="emit('document')"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
                <line x1="10" y1="9" x2="8" y2="9"></line>
              </svg>
              {{ t('chat.upload_document') }}
            </button>
            <button
              v-if="allowKnowledge !== false"
              class="flex w-full items-center gap-2 whitespace-nowrap px-3 py-2 text-sm hover:bg-slate-50"
              :class="knowledgeQaEnabled ? 'bg-blue-50 text-blue-700' : 'text-slate-700'"
              :aria-pressed="knowledgeQaEnabled"
              @click="emit('knowledge')"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"></path>
                <path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4"></path>
                <path d="M12 17h.01"></path>
              </svg>
              {{ knowledgeLabel }}
            </button>
          </div>
        </div>
</template>
