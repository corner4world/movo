<script setup lang="ts">
import type { RecordingAnalysis } from '../../api/recording'
import { recordingReviewMessages, recordingReviewUi } from '../../locales/recordingReviewMessages'

const props = defineProps<{
  show: boolean
  loading: boolean
  saving: boolean
  analysis: RecordingAnalysis | null
  error: string
  locale: 'zh' | 'en'
}>()

defineEmits<{
  (event: 'save'): void
  (event: 'discard'): void
  (event: 'retry'): void
}>()

function reasonLabel(reason: string): string {
  return recordingReviewMessages[reason as keyof typeof recordingReviewMessages]?.[props.locale] || reason
}

function copy(key: keyof typeof recordingReviewUi, count?: number): string {
  const value = recordingReviewUi[key][props.locale]
  return count === undefined ? value : value.replace('{count}', String(count))
}
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="recording-review-backdrop" role="presentation">
      <section
        class="recording-review-dialog"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="'recording-review-title'"
      >
        <header class="dialog-header">
          <div>
            <p class="eyebrow">{{ copy('eyebrow') }}</p>
            <h2 id="recording-review-title">{{ copy('title') }}</h2>
          </div>
          <span v-if="analysis" class="step-count">
            {{ copy('replayableSteps', analysis.steps.length) }}
          </span>
        </header>

        <div v-if="loading" class="dialog-state" role="status">
          <span class="spinner" aria-hidden="true"></span>
          <span>{{ copy('detecting') }}</span>
        </div>

        <template v-else-if="analysis">
          <div class="workflow-name">
            <span>{{ copy('generatedName') }}</span>
            <strong>{{ analysis.display_name }}</strong>
          </div>

          <div v-if="!analysis.complete" class="validation-error" role="alert">
            <strong>{{ copy('incomplete') }}</strong>
            <ul>
              <li v-for="reason in analysis.reasons" :key="reason">{{ reasonLabel(reason) }}</li>
            </ul>
          </div>

          <ol class="step-list" :aria-label="copy('detectedSteps')">
            <li v-for="step in analysis.steps" :key="step.index">
              <span class="step-index">{{ step.index }}</span>
              <span class="step-label">{{ step.label }}</span>
              <span v-if="step.parameterized" class="parameter-tag">
                {{ copy('parameterized') }}
              </span>
            </li>
          </ol>
        </template>

        <div v-else class="dialog-state error" role="alert">
          {{ error || (copy('analysisFailed')) }}
        </div>

        <footer class="dialog-footer">
          <button type="button" class="secondary" :disabled="saving" @click="$emit('discard')">
            {{ copy('discard') }}
          </button>
          <button
            v-if="analysis && !analysis.complete"
            type="button"
            class="secondary"
            :disabled="loading || saving"
            @click="$emit('retry')"
          >
            {{ copy('analyzeAgain') }}
          </button>
          <button
            type="button"
            class="primary"
            :disabled="loading || saving || !analysis?.complete"
            @click="$emit('save')"
          >
            {{ saving ? (copy('saving')) : (copy('save')) }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.recording-review-backdrop { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: 24px; background: rgb(15 23 42 / .46); }
.recording-review-dialog { display: flex; width: min(680px, 100%); max-height: min(760px, calc(100vh - 48px)); flex-direction: column; overflow: hidden; border: 1px solid #dbe3ef; border-radius: 14px; background: #fff; box-shadow: 0 24px 70px rgb(15 23 42 / .22); color: #1e293b; }
.dialog-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; border-bottom: 1px solid #e2e8f0; padding: 20px 22px 16px; }
.eyebrow { margin: 0 0 3px; color: #2563eb; font-size: 12px; font-weight: 600; }
h2 { margin: 0; color: #0f172a; font-size: 19px; line-height: 1.35; }
.step-count { flex: none; border-radius: 999px; background: #eff6ff; padding: 5px 9px; color: #1d4ed8; font-size: 12px; }
.workflow-name { display: grid; gap: 5px; margin: 18px 22px 0; border: 1px solid #dbeafe; border-radius: 10px; background: #f8fbff; padding: 12px 14px; }
.workflow-name span { color: #64748b; font-size: 12px; }
.workflow-name strong { color: #0f172a; font-size: 15px; }
.validation-error { margin: 14px 22px 0; border: 1px solid #fecaca; border-radius: 10px; background: #fef2f2; padding: 11px 14px; color: #991b1b; font-size: 13px; line-height: 1.55; }
.validation-error ul { margin: 5px 0 0; padding-left: 20px; }
.step-list { min-height: 120px; margin: 16px 22px; overflow: auto; border: 1px solid #e2e8f0; border-radius: 10px; padding: 0; list-style: none; }
.step-list li { display: flex; min-height: 48px; align-items: center; gap: 10px; border-bottom: 1px solid #f1f5f9; padding: 8px 12px; }
.step-list li:last-child { border-bottom: 0; }
.step-index { display: grid; width: 26px; height: 26px; flex: none; place-items: center; border-radius: 50%; background: #f1f5f9; color: #475569; font-size: 12px; font-weight: 600; }
.step-label { min-width: 0; flex: 1; overflow: hidden; color: #334155; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.parameter-tag { flex: none; border-radius: 5px; background: #ecfdf5; padding: 3px 6px; color: #047857; font-size: 10px; }
.dialog-state { display: flex; min-height: 220px; align-items: center; justify-content: center; gap: 10px; padding: 32px; color: #475569; font-size: 14px; }
.dialog-state.error { color: #b91c1c; }
.spinner { width: 18px; height: 18px; border: 2px solid #bfdbfe; border-top-color: #2563eb; border-radius: 50%; animation: spin .8s linear infinite; }
.dialog-footer { display: flex; justify-content: flex-end; gap: 10px; border-top: 1px solid #e2e8f0; padding: 14px 22px; }
.dialog-footer button { min-width: 96px; min-height: 44px; border-radius: 8px; padding: 0 16px; font-size: 13px; font-weight: 600; cursor: pointer; }
.dialog-footer .secondary { border: 1px solid #cbd5e1; background: #fff; color: #475569; }
.dialog-footer .primary { border: 1px solid #2563eb; background: #2563eb; color: #fff; }
.dialog-footer button:disabled { cursor: default; opacity: .48; }
.dialog-footer button:focus-visible { outline: 3px solid #bfdbfe; outline-offset: 2px; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spinner { animation: none; } }
@media (max-width: 560px) { .recording-review-backdrop { padding: 10px; } .dialog-header { align-items: flex-start; } .step-count { display: none; } .step-list { margin-inline: 14px; } .workflow-name, .validation-error { margin-inline: 14px; } }
</style>
