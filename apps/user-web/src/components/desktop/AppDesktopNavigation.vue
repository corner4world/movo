<script setup lang="ts">
import type { CodePaneState } from '../../composables/code/useDshCodeRuntime'
import type { AppView } from '../../composables/useAppNavigation'
import { t } from '../../composables/i18n'
import { capabilities } from '../../platform'
import type { DshWorkspace, DshWorkspaceSummary } from '../../platform/types'
import type { DesktopToolTabKind } from './desktopToolTabs'
import DesktopWindowChrome from './DesktopWindowChrome.vue'
import DesktopPrimaryNavigation, { type DesktopPrimarySection } from './DesktopPrimaryNavigation.vue'
import WindowsTitleBar from './WindowsTitleBar.vue'

defineProps<{
  windows: boolean
  collapsed: boolean
  dark: boolean
  locale: 'zh' | 'en'
  navigationWidth: number
  section: DesktopPrimarySection
  title: string
  view: AppView
  sessionId: string | null
  userId: string | null
  mainId: string
  authToken: string
  membersRevision?: number
  codeState: CodePaneState
  workspaceSummary: DshWorkspaceSummary | null
  hasMessages: boolean
  activeTool: DesktopToolTabKind | null
  codeAvailable: boolean
  browserAvailable: boolean
  workspaces: readonly DshWorkspace[]
  workspacesLoading: boolean
  skillsAvailable: boolean
  toolsAvailable: boolean
  knowledgeAvailable: boolean
  skillBadge: number
  knowledgeBadge: number
  loggedIn: boolean
  avatarUrl: string
  avatarText: string
  accountLabel: string
}>()

const emit = defineEmits<{
  (event: 'toggle-sidebar'): void
  (event: 'new-chat'): void
  (event: 'add-project'): void
  (event: 'session-left', sessionId: string): void
  (event: 'choose-workspace'): void
  (event: 'select-workspace', workspace: DshWorkspace): void
  (event: 'clear-workspace'): void
  (event: 'worktree', enabled: boolean): void
  (event: 'source-ref', fullRef: string): void
  (event: 'branch-updated', branch: string): void
  (event: 'open-browser'): void
  (event: 'toggle-code-panel', mode: 'changes' | 'files' | 'terminal'): void
  (event: 'back'): void
  (event: 'navigate', section: DesktopPrimarySection): void
  (event: 'account'): void
  (event: 'avatar-error', value: Event): void
}>()
</script>

<template>
  <WindowsTitleBar
    v-if="windows"
    :collapsed="collapsed"
    :dark="dark"
    :locale="locale"
    @toggle-sidebar="emit('toggle-sidebar')"
    @new-chat="emit('new-chat')"
    @add-project="emit('add-project')"
  />
  <DesktopWindowChrome
    :navigation-width="navigationWidth"
    :windows-title-bar="windows"
    :sidebar-collapsed="collapsed"
    :secondary-navigation-available="section === 'home'"
    :title="title"
    :show-back="view === 'skills'"
    :back-label="t('skills.back_to_chat')"
    :chat-actions="view === 'chat'"
    :session-id="sessionId || undefined"
    :user-id="userId || undefined"
    :main-id="mainId"
    :auth-token="authToken"
    :members-revision="membersRevision"
    :workspace="codeState.workspace"
    :show-workspace-context="hasMessages"
    :workspace-branch="workspaceSummary?.branch || codeState.session?.git_branch || codeState.workspace?.git_branch || ''"
    :workspace-source-ref="codeState.sourceRef"
    :workspace-detached="codeState.session?.detached_head"
    :code-session-active="Boolean(codeState.session)"
    :workspace-busy="codeState.busy"
    :worktree="codeState.worktree"
    :locale="locale"
    :active-tool="activeTool"
    :git-available="workspaceSummary?.git_available === true"
    :change-count="workspaceSummary?.changes.length || 0"
    :files-available="capabilities.workspaceFiles"
    :terminal-available="capabilities.projectTerminal"
    :code-available="codeAvailable"
    :browser-available="browserAvailable"
    :workspaces="workspaces"
    :workspaces-loading="workspacesLoading"
    @session-left="emit('session-left', $event)"
    @choose-workspace="emit('choose-workspace')"
    @select-workspace="emit('select-workspace', $event)"
    @clear-workspace="emit('clear-workspace')"
    @worktree="emit('worktree', $event)"
    @source-ref="emit('source-ref', $event)"
    @branch-updated="emit('branch-updated', $event)"
    @open-browser="emit('open-browser')"
    @toggle-code-panel="emit('toggle-code-panel', $event)"
    @back="emit('back')"
    @toggle-sidebar="emit('toggle-sidebar')"
  />
  <DesktopPrimaryNavigation
    :active="section"
    :locale="locale"
    :skills-available="skillsAvailable"
    :tools-available="toolsAvailable"
    :knowledge-available="knowledgeAvailable"
    :skill-badge="skillBadge"
    :knowledge-badge="knowledgeBadge"
    :logged-in="loggedIn"
    :avatar-url="avatarUrl"
    :avatar-text="avatarText"
    :account-label="accountLabel"
    @navigate="emit('navigate', $event)"
    @account="emit('account')"
    @avatar-error="emit('avatar-error', $event)"
  />
</template>
