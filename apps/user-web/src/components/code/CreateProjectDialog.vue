<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NModal, NRadio, NRadioGroup } from 'naive-ui'
import type { DshWorkspace } from '../../platform/types'
import { t } from '../../composables/i18n'

const props = defineProps<{ show: boolean; workspace: DshWorkspace | null; worktree: boolean; busy?: boolean; selecting?: boolean; selectionPhase?: string; selectionError?: string }>()
const emit = defineEmits<{ (event: 'update:worktree', value: boolean): void; (event: 'choose-folder'): void; (event: 'create'): void; (event: 'close'): void }>()

const projectName = computed(() => {
  if (!props.workspace) return ''
  const normalizedPath = props.workspace.path.replace(/[\\/]+$/, '')
  return normalizedPath.split(/[\\/]/).pop() || props.workspace.title
})
const canCreate = computed(() => Boolean(props.workspace && !props.busy && !props.selecting))
</script>

<template>
  <NModal :show="show" preset="card" :mask-closable="!busy" :closable="!busy" style="width:440px" :title="t('projectDialog.create')" @update:show="(value) => !value && emit('close')">
    <div class="project-dialog">
      <section class="field-group">
        <span class="field-label">{{ t('projectDialog.localFolder') }}</span>
        <div class="folder-row">
          <div class="folder-details">
            <strong>{{ projectName || t('projectDialog.noFolder') }}</strong>
            <span :title="workspace?.path">{{ workspace?.path || t('projectDialog.folderNameHint') }}</span>
          </div>
          <NButton size="small" :loading="selecting" :disabled="busy || selecting" @click="emit('choose-folder')">{{ t('projectDialog.chooseFolder') }}</NButton>
        </div>
        <p v-if="selectionError" class="folder-error" role="alert">{{ selectionError }}</p>
        <p v-else-if="selecting && selectionPhase" class="folder-progress" role="status">{{ selectionPhase }}</p>
      </section>
      <section class="field-group">
        <span class="field-label">{{ t('projectDialog.changeMode') }}</span>
        <NRadioGroup :value="worktree" :disabled="busy" @update:value="(value) => emit('update:worktree', Boolean(value))">
          <div class="mode-options">
            <NRadio :value="false"><span class="mode-copy"><strong>{{ t('projectDialog.editLocally') }}</strong><small>{{ t('projectDialog.currentBranch') }}</small></span></NRadio>
            <NRadio :value="true"><span class="mode-copy"><strong>{{ t('projectDialog.newWorktree') }}</strong><small>{{ t('projectDialog.worktreeHint') }}</small></span></NRadio>
          </div>
        </NRadioGroup>
      </section>
    </div>
    <template #footer><div class="dialog-actions"><NButton :disabled="busy" @click="emit('close')">{{ t('ui.cancel') }}</NButton><NButton type="primary" :loading="busy" :disabled="!canCreate" @click="emit('create')">{{ t('projectDialog.create') }}</NButton></div></template>
  </NModal>
</template>

<style scoped>
.project-dialog{display:flex;flex-direction:column;gap:18px}.field-group{display:flex;flex-direction:column;gap:8px}.field-label{color:#475569;font-size:13px;font-weight:600}.folder-row{display:flex;min-width:0;align-items:center;gap:8px}.folder-details{display:flex;min-width:0;flex:1;flex-direction:column;gap:2px;overflow:hidden;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc;padding:8px 10px}.folder-details strong{overflow:hidden;color:#334155;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.folder-details span{overflow:hidden;color:#94a3b8;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.mode-options{display:grid;grid-template-columns:1fr 1fr;gap:8px}.mode-options :deep(.n-radio){align-items:flex-start;margin:0;border:1px solid #e2e8f0;border-radius:8px;padding:9px;transition:border-color .15s,background-color .15s}.mode-options :deep(.n-radio--checked){border-color:#93c5fd;background:#eff6ff}.mode-options :deep(.n-radio__label){min-width:0}.mode-copy{display:flex;flex-direction:column;gap:2px}.mode-copy strong{color:#334155;font-size:12px;line-height:18px}.mode-copy small{color:#94a3b8;font-size:10px;line-height:14px}.dialog-actions{display:flex;justify-content:flex-end;gap:8px}
.folder-error{margin:0;color:#d03050;font-size:12px;line-height:1.5;overflow-wrap:anywhere}
.folder-progress{margin:0;color:#7a8ca9;font-size:12px;line-height:1.5}
</style>
