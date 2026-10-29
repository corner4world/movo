<template>
  <span v-if="status" class="environment-badge" @click.stop>
    <n-tag size="small" :bordered="false" :type="status === 'ready' ? 'success' : status === 'failed' ? 'error' : 'warning'">
      <span v-if="status === 'preparing'" class="environment-spinner" aria-hidden="true" />
      {{ t(`skillDeps.status.${status}`) }}
    </n-tag>
    <n-button v-if="status === 'failed' || status === 'unavailable'" size="tiny" text type="primary" :loading="busy" @click.stop="emit('retry')">
      {{ t('skillDeps.retry') }}
    </n-button>
  </span>
</template>

<script setup lang="ts">
import { NButton, NTag } from 'naive-ui'
import { t } from '../../composables/i18n'

defineProps<{ status?: string | null; busy?: boolean }>()
const emit = defineEmits<{ retry: [] }>()
</script>

<style scoped>
.environment-badge { display: flex; align-items: center; gap: 6px; min-height: 22px; margin: 0 0 8px; }
.environment-spinner { display: inline-block; width: 11px; height: 11px; margin-right: 4px; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; vertical-align: -1px; animation: environment-spin .8s linear infinite; }
@keyframes environment-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .environment-spinner { animation: none; } }
</style>
