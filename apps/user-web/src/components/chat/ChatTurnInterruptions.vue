<script setup lang="ts">
import UserQuestionPanel from './UserQuestionPanel.vue'
import SessionRunNotice from './SessionRunNotice.vue'
import ToolApprovalPrompt from '../execution/ToolApprovalPrompt.vue'
import DshCodeApprovalList from '../code/DshCodeApprovalList.vue'
import type { useUserQuestions } from '../../composables/useUserQuestions'
import type { useDshToolApprovals } from '../../composables/useDshToolApprovals'
import type { DshPendingApproval } from '../../platform/types'

const props = defineProps<{
  questions: ReturnType<typeof useUserQuestions>
  approvals: ReturnType<typeof useDshToolApprovals>
  foreignRunActive: boolean
  foreignRunFinished: boolean
  foreignRunSpeakerName: string
  refreshingSession: boolean
  codeError?: string
  codeApprovals?: DshPendingApproval[]
  codeApprovalBusy?: Record<string, boolean>
}>()
const emit = defineEmits<{
  (e: 'refresh-session'): void
  (e: 'code-approval', approvalId: string, decision: 'approved' | 'rejected', scope: 'once' | 'session'): void
}>()
</script>

<template>
  <div v-if="questions.pending.value.length" class="mx-auto w-full max-w-4xl px-4 md:px-6">
    <UserQuestionPanel
      v-for="question in questions.pending.value"
      :key="question.id"
      :item="question"
      :busy="questions.busy.value"
      :error="questions.error.value"
      @submit="answers => questions.answer(question, answers)"
    />
  </div>
  <div v-if="foreignRunActive || foreignRunFinished" class="px-4 md:px-6">
    <SessionRunNotice
      :running="foreignRunActive"
      :speaker-name="foreignRunSpeakerName"
      :refreshing="refreshingSession"
      @refresh="emit('refresh-session')"
    />
  </div>
  <div v-if="codeError" class="mx-auto w-full max-w-4xl px-4 md:px-6">
    <div class="mb-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs leading-5 text-red-700" role="alert">
      {{ codeError }}
    </div>
  </div>
  <div v-if="approvals.active.value.length" class="mx-auto w-full max-w-4xl px-4 md:px-6">
    <ToolApprovalPrompt
      v-for="approval in approvals.active.value"
      :key="approval.id"
      :item="approval"
      :busy="Boolean(approvals.busy.value[approval.id])"
      :error="approvals.errors.value[approval.id] || ''"
      @decide="(decision, grantScope) => approvals.decide(approval, decision, grantScope)"
    />
  </div>
  <div v-if="codeApprovals?.length" class="mx-auto w-full max-w-4xl px-4 md:px-6">
    <DshCodeApprovalList
      :approvals="codeApprovals"
      :busy="codeApprovalBusy"
      :error="codeError"
      @decide="(approvalId, decision, scope) => emit('code-approval', approvalId, decision, scope)"
    />
  </div>
</template>
