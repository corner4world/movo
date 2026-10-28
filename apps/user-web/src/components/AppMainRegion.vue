<script setup lang="ts">
import type { SessionSummary } from '../api/sessions'
import type { AppView } from '../composables/useAppNavigation'
import ChatSessionHeader from './chat/ChatSessionHeader.vue'
import AppFeaturePages from './AppFeaturePages.vue'

defineProps<{
  desktop: boolean
  currentView: AppView
  currentSessionId: string | null
  chatHeaderTitle: string
  userId: string | null
  mainId: string
  authToken: string
  membersRevision?: number
  selectedSkill: any
  pendingSkillShareActionCount: number
  pendingSkillFeedbackCount: number
  personalKnowledgeShareCount: number
  personalKnowledgeUnreadCount: number
  sessions: SessionSummary[]
  scheduledTaskInitialSessionId: string | null
  scheduledTaskInitialPrompt: string
  scheduledTaskCreateRequestKey: number
  timezoneValue: string
}>()

const emit = defineEmits<{
  (event: 'session-left', sessionId: string): void
  (event: 'configure', skill: any): void
  (event: 'login'): void
  (event: 'share-count-change'): void
  (event: 'knowledge-viewed'): void
  (event: 'skill-back'): void
  (event: 'skill-saved', skill: any): void
  (event: 'composite-saved', skill: any): void
  (event: 'remove-skill', skill: any): void
  (event: 'scheduled-back'): void
  (event: 'open-session', id: string): void
  (event: 'usage-back'): void
}>()
</script>

<template>
  <main class="app-main flex-1 flex flex-col min-w-0 min-h-0 bg-white">
    <ChatSessionHeader
      v-if="!desktop && currentView === 'chat' && currentSessionId"
      :session-id="currentSessionId"
      :title="chatHeaderTitle"
      :user-id="userId || ''"
      :main-id="mainId"
      :auth-token="authToken"
      :refresh-token="membersRevision"
      @left="emit('session-left', $event)"
    />

    <div class="flex-1 flex min-w-0 min-h-0 overflow-hidden">
      <AppFeaturePages
        v-if="currentView !== 'chat'"
        :current-view="currentView"
        :user-id="userId"
        :main-id="mainId"
        :auth-token="authToken"
        :selected-skill="selectedSkill"
        :pending-skill-share-action-count="pendingSkillShareActionCount"
        :pending-skill-feedback-count="pendingSkillFeedbackCount"
        :personal-knowledge-share-count="personalKnowledgeShareCount"
        :personal-knowledge-unread-count="personalKnowledgeUnreadCount"
        :sessions="sessions"
        :current-session-id="currentSessionId"
        :scheduled-task-initial-session-id="scheduledTaskInitialSessionId"
        :scheduled-task-initial-prompt="scheduledTaskInitialPrompt"
        :scheduled-task-create-request-key="scheduledTaskCreateRequestKey"
        :timezone-value="timezoneValue"
        @configure="emit('configure', $event)"
        @login="emit('login')"
        @share-count-change="emit('share-count-change')"
        @knowledge-viewed="emit('knowledge-viewed')"
        @skill-back="emit('skill-back')"
        @skill-saved="emit('skill-saved', $event)"
        @composite-saved="emit('composite-saved', $event)"
        @remove-skill="emit('remove-skill', $event)"
        @scheduled-back="emit('scheduled-back')"
        @open-session="emit('open-session', $event)"
        @usage-back="emit('usage-back')"
      />
      <div v-else class="flex-1 relative overflow-hidden min-h-0">
        <slot name="chat" />
      </div>
    </div>
  </main>
</template>
