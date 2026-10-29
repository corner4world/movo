<template>
  <span v-if="status" class="environment-badge" @click.stop>
    <n-tag size="small" :bordered="false" :type="status === 'ready' ? 'success' : status === 'failed' ? 'error' : 'warning'">
      {{ t(`skillDeps.status.${status}`) }}
    </n-tag>
    <n-button v-if="status === 'failed' || status === 'unavailable'" size="tiny" text type="primary" :loading="busy" @click.stop="emit('retry')">
      {{ t('skillDeps.retry') }}
    </n-button>
  </span>
</template>

<script setup lang="ts">
import { NButton, NTag } from 'naive-ui'
import { t } from '@/composables/i18n'

defineProps<{ status?: string | null; busy?: boolean }>()
const emit = defineEmits<{ retry: [] }>()
</script>

<style scoped>.environment-badge{display:inline-flex;align-items:center;gap:6px}</style>
