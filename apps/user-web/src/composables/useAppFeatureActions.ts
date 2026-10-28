import type { Ref } from 'vue'
import type { AppView } from './useAppNavigation'

type ScheduledTaskOptions = { prompt?: string; sessionId?: string | null; create?: boolean }

type FeatureActionOptions = {
  isLoggedIn: Ref<boolean>
  currentSessionId: Ref<string | null>
  scheduledTaskInitialPrompt: Ref<string>
  scheduledTaskInitialSessionId: Ref<string | null>
  scheduledTaskCreateRequestKey: Ref<number>
  selectedSkill: Ref<any>
  sessionSearchOpen: Ref<boolean>
  navigateTo: (view: AppView) => void
  openLogin: () => void
  closeUserMenu: () => void
  closeSessionSearch: () => void
  startLocalSession: (options: { inheritCurrentProject: true }) => void
  loadSkills: () => Promise<unknown>
  refreshSkillShareCount: () => unknown
  refreshPersonalKnowledgeCount: () => unknown
}

/** Navigation and editor actions shared by the sidebar, chat, and feature pages. */
export function useAppFeatureActions(options: FeatureActionOptions) {
  const {
    isLoggedIn, currentSessionId, scheduledTaskInitialPrompt,
    scheduledTaskInitialSessionId, scheduledTaskCreateRequestKey, selectedSkill,
    sessionSearchOpen, navigateTo, openLogin, closeUserMenu, closeSessionSearch,
    startLocalSession, loadSkills, refreshSkillShareCount, refreshPersonalKnowledgeCount,
  } = options

  function openTokenUsagePage() {
    navigateTo('token-usage')
    closeUserMenu()
  }

  function closeTokenUsagePage() {
    navigateTo('chat')
  }

  function openScheduledTasks(task: ScheduledTaskOptions = {}) {
    if (!isLoggedIn.value) {
      openLogin()
      return
    }
    scheduledTaskInitialPrompt.value = task.prompt || ''
    scheduledTaskInitialSessionId.value = task.sessionId ?? currentSessionId.value
    if (task.create) scheduledTaskCreateRequestKey.value += 1
    navigateTo('scheduled-tasks')
    closeSessionSearch()
  }

  function handleSidebarAction(icon: string) {
    if (icon === 'plus') startLocalSession({ inheritCurrentProject: true })
    else if (icon === 'clock') openScheduledTasks()
    else openSessionSearch()
  }

  function openSessionSearch() {
    if (!isLoggedIn.value) {
      openLogin()
      return
    }
    navigateTo('chat')
    sessionSearchOpen.value = true
  }

  function openSkillsPage() {
    navigateTo('skills')
    void loadSkills()
    void refreshSkillShareCount()
  }

  function closeSkillsPage() {
    navigateTo('chat')
  }

  function openToolsPage() {
    navigateTo('tools')
  }

  function openKnowledgePage() {
    navigateTo('knowledge')
    void refreshPersonalKnowledgeCount()
  }

  function openDesktopPrimarySection(section: 'home' | 'scheduled' | 'skills' | 'plugins' | 'tools' | 'knowledge') {
    if (section === 'home') navigateTo('chat')
    else if (section === 'scheduled') openScheduledTasks()
    else if (section === 'skills') openSkillsPage()
    else if (section === 'plugins') navigateTo('plugins')
    else if (section === 'tools') openToolsPage()
    else openKnowledgePage()
  }

  function openSkillConfig(skill: any) {
    selectedSkill.value = skill
    const kind = String(skill?.skill_type || skill?.role || '').toLowerCase()
    navigateTo(kind === 'composite_task' ? 'composite-editor' : 'skill-config')
  }

  function openNewCompositeSkill() {
    selectedSkill.value = null
    navigateTo('composite-editor')
  }

  function closeSkillConfig() {
    navigateTo('skills')
  }

  function handleCompositeSaved(savedSkill: any) {
    selectedSkill.value = savedSkill || selectedSkill.value
    void loadSkills().catch(() => {})
    navigateTo('skills')
  }

  function handleSkillConfigSaved(savedSkill: any) {
    selectedSkill.value = savedSkill || selectedSkill.value
    void loadSkills().catch(() => {})
  }

  return {
    openTokenUsagePage, closeTokenUsagePage, openScheduledTasks, handleSidebarAction, openSessionSearch,
    openSkillsPage, closeSkillsPage, openToolsPage, openKnowledgePage,
    openDesktopPrimarySection, openSkillConfig, openNewCompositeSkill,
    closeSkillConfig, handleCompositeSaved, handleSkillConfigSaved,
  }
}
