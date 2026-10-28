<script setup lang="ts">
import { ref } from 'vue'
import type { ChatModelOption } from '../../api/models'
defineProps<{
  models: ChatModelOption[]
  selectedModelId: string
  modelSelectorLabel: string
  modelLoadError?: string
  running: boolean
  blocked?: boolean
  open: boolean
}>()
const emit = defineEmits<{
  (e: 'toggle'): void
  (e: 'select', modelId: string): void
}>()
const root = ref<HTMLElement | null>(null)
defineExpose({ root })
</script>

<template>
<div ref="root" class="relative min-w-0">
  <button
    type="button"
    class="group flex h-7 max-w-[240px] items-center gap-1 rounded-md px-1.5 text-[11px] font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-100"
    :class="running || blocked ? 'cursor-not-allowed opacity-70' : 'cursor-pointer'"
    :title="modelLoadError || modelSelectorLabel"
    :disabled="running || blocked"
    @click="emit('toggle')"
  >
    <span class="truncate text-left">{{ modelSelectorLabel }}</span>
    <svg class="h-3 w-3 shrink-0 text-slate-400" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M6 12l4-4 4 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
  </button>
  <div
    v-if="open"
    class="absolute bottom-9 right-0 z-40 w-[320px] max-w-[calc(100vw-32px)] overflow-hidden rounded-2xl border border-slate-200 bg-white py-1.5 shadow-xl shadow-slate-900/10"
  >
    <button v-if="models.length === 0" type="button" class="flex w-full items-center gap-3 px-3 py-2.5 text-left" @click="emit('select', '')">
      <span class="min-w-0 flex-1"><span class="block truncate text-sm font-medium text-slate-800">{{ modelSelectorLabel }}</span></span>
    </button>
    <button
      v-for="model in models"
      :key="model.id"
      type="button"
      class="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-slate-50"
      :class="model.id === selectedModelId ? 'bg-blue-50/80' : ''"
      @click="emit('select', model.id)"
    >
      <span class="min-w-0 flex-1">
        <span class="flex min-w-0 items-center gap-2">
          <span class="truncate text-sm font-medium text-slate-900">{{ model.displayName || model.modelName }}</span>
        </span>
        <span class="block truncate text-xs text-slate-500">{{ model.providerName }} · {{ model.modelName }}</span>
      </span>
      <svg v-if="model.id === selectedModelId" class="h-4 w-4 shrink-0 text-blue-600" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M5 10.5l3 3L15 6.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" /></svg>
    </button>
  </div>
</div>
</template>
